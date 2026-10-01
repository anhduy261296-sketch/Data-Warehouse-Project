from __future__ import annotations
import datetime as dt
import logging
from typing import Any, Sequence
logger = logging.getLogger(__name__)
SOURCE_QUERY = '\n    SELECT *\n    FROM public.sp_syn_dms_sales_orders(%(start_at)s::timestamp, %(end_at)s::timestamp)\n    WHERE "Sku" IS NOT NULL\n      AND "OrderType" NOT IN (\'DGH\', \'LR\', \'TEST_LOYALTY\')\n      AND "OrderStatus" NOT IN (\'draft\')\n'
TARGET_SCHEMA = 'dbo'
TARGET_TABLE = 'DMS_SO'
LOG_TABLE = 'DMS_SO_Load_Log'
PENDING_TABLE = 'DMS_SO_Pending'
TERMINAL_STATUSES = {'done', 'cancel', 'refused'}

def _window_already_loaded(target_conn: Any, start_at: str, end_at: str) -> bool:
    cursor = target_conn.cursor()
    cursor.execute(f"\n        SELECT TOP 1 1\n        FROM {TARGET_SCHEMA}.{LOG_TABLE}\n        WHERE start_at = %s AND end_at = %s AND status = 'SUCCESS'\n        ", (start_at, end_at))
    return cursor.fetchone() is not None

def _fetch_source_rows(source_conn: Any, start_at: str, end_at: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    cursor = source_conn.cursor()
    cursor.execute(SOURCE_QUERY, {'start_at': start_at, 'end_at': end_at})
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    return (columns, [tuple(row) for row in rows])

def _delete_window(target_conn: Any, start_at: str, end_at: str) -> None:
    cursor = target_conn.cursor()
    cursor.execute(f'DELETE FROM {TARGET_SCHEMA}.{TARGET_TABLE} WHERE DocDate >= %s AND DocDate < %s', (start_at, end_at))

def _insert_rows(target_conn: Any, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    if not rows:
        return
    quoted_cols = ', '.join((f'[{c}]' for c in columns))
    placeholders = ', '.join(('%s' for _ in columns))
    insert_sql = f'INSERT INTO {TARGET_SCHEMA}.{TARGET_TABLE} ({quoted_cols}) VALUES ({placeholders})'
    cursor = target_conn.cursor()
    if hasattr(cursor, 'fast_executemany'):
        cursor.fast_executemany = True
    cursor.executemany(insert_sql, list(rows))

def _log_window(target_conn: Any, start_at: str, end_at: str, row_count: int, status: str) -> None:
    cursor = target_conn.cursor()
    cursor.execute(f'\n        INSERT INTO {TARGET_SCHEMA}.{LOG_TABLE} (start_at, end_at, row_count, status, loaded_at)\n        VALUES (%s, %s, %s, %s, SYSUTCDATETIME())\n        ', (start_at, end_at, row_count, status))

def _sync_pending_table(target_conn: Any, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    """Cap nhat DMS_SO_Pending tu cac dong vua fetch duoc (window moi hoac
    window recheck deu goi ham nay). Don nao OrderStatus (moi nhat trong lo
    dong vua fetch) thuoc TERMINAL_STATUSES (done/cancel/refused) thi xoa
    khoi pending (khong can check lai nua); con lai (to_approve/sale/...)
    thi upsert vao pending de lan sau recheck tiep."""
    if not rows:
        return
    try:
        code_idx = columns.index('OrderCode')
        status_idx = columns.index('OrderStatus')
        date_idx = columns.index('DocDate')
    except ValueError:
        logger.warning('Khong tim thay cot OrderCode/OrderStatus/DocDate trong ket qua nguon - bo qua cap nhat %s.', PENDING_TABLE)
        return

    latest_status: dict[str, str] = {}
    latest_date: dict[str, Any] = {}
    for row in rows:
        code = row[code_idx]
        if not code:
            continue
        latest_status[code] = row[status_idx]
        latest_date[code] = row[date_idx]

    terminal_codes = sorted((c for c, s in latest_status.items() if s in TERMINAL_STATUSES))
    pending_codes = [c for c, s in latest_status.items() if s not in TERMINAL_STATUSES]

    cursor = target_conn.cursor()
    if terminal_codes:
        placeholders = ', '.join(('%s' for _ in terminal_codes))
        cursor.execute(f'DELETE FROM {TARGET_SCHEMA}.{PENDING_TABLE} WHERE OrderCode IN ({placeholders})', tuple(terminal_codes))

    for code in pending_codes:
        doc_date = latest_date[code]
        doc_date = doc_date.date() if hasattr(doc_date, 'date') else doc_date
        cursor.execute(f'\n            MERGE {TARGET_SCHEMA}.{PENDING_TABLE} AS target\n            USING (SELECT %s AS OrderCode, %s AS DocDate) AS source\n            ON target.OrderCode = source.OrderCode\n            WHEN MATCHED THEN\n                UPDATE SET LastCheckedAt = SYSUTCDATETIME()\n            WHEN NOT MATCHED THEN\n                INSERT (OrderCode, DocDate, FirstSeenAt, LastCheckedAt)\n                VALUES (source.OrderCode, source.DocDate, SYSUTCDATETIME(), SYSUTCDATETIME());\n            ', (code, doc_date))

def _get_pending_days(target_conn: Any, before_date: str) -> list[str]:
    cursor = target_conn.cursor()
    cursor.execute(f'SELECT DISTINCT DocDate FROM {TARGET_SCHEMA}.{PENDING_TABLE} WHERE DocDate < %s ORDER BY DocDate', (before_date,))
    result = []
    for d, in cursor.fetchall():
        result.append(d.isoformat() if hasattr(d, 'isoformat') else str(d)[:10])
    return result

def _sync_window(source_conn: Any, target_conn: Any, start_at: str, end_at: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    """Xoa + fetch + insert lai TOAN BO 1 khoang (dung cho recheck pending -
    khac voi sync_dms_sales_orders chinh van giu idempotent-skip cho window
    moi, vi recheck can ghi de du lieu cu da loi thoi)."""
    columns, rows = _fetch_source_rows(source_conn, start_at, end_at)
    _delete_window(target_conn, start_at, end_at)
    _insert_rows(target_conn, columns, rows)
    return columns, rows

def sync_dms_sales_orders(source_conn: Any, target_conn: Any, *, start_at: str, end_at: str, **_ignored: Any) -> int:
    total = 0
    if not _window_already_loaded(target_conn, start_at, end_at):
        columns, rows = _fetch_source_rows(source_conn, start_at, end_at)
        try:
            _insert_rows(target_conn, columns, rows)
            _log_window(target_conn, start_at, end_at, len(rows), 'SUCCESS')
            target_conn.commit()
            total += len(rows)
            _sync_pending_table(target_conn, columns, rows)
            target_conn.commit()
            logger.info('Da insert %d dong vao %s.%s cho window %s -> %s', len(rows), TARGET_SCHEMA, TARGET_TABLE, start_at, end_at)
        except Exception:
            target_conn.rollback()
            _log_window(target_conn, start_at, end_at, 0, 'FAILED')
            target_conn.commit()
            raise
    else:
        logger.info('Window %s -> %s da load roi, bo qua insert moi (idempotent) - van se recheck cac ngay con pending.', start_at, end_at)

    # Recheck cac ngay CU (truoc window hien tai) con don chua terminal -
    # xoa + pull lai NGUYEN NGAY do tu nguon song de cap nhat status moi
    # nhat (to_approve/sale co the da thanh done/cancel/refused).
    window_start_date = start_at[:10]
    for day in _get_pending_days(target_conn, window_start_date):
        day_start = f'{day} 00:00:00'
        day_end = (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat() + ' 00:00:00'
        try:
            day_columns, day_rows = _sync_window(source_conn, target_conn, day_start, day_end)
            _log_window(target_conn, day_start, day_end, len(day_rows), 'SUCCESS')
            target_conn.commit()
            total += len(day_rows)
            _sync_pending_table(target_conn, day_columns, day_rows)
            target_conn.commit()
            logger.info('Recheck pending %s: %d dong (xoa + nap lai tu nguon).', day, len(day_rows))
        except Exception:
            target_conn.rollback()
            _log_window(target_conn, day_start, day_end, 0, 'FAILED')
            target_conn.commit()
            raise

    return total
