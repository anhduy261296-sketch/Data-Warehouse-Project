from __future__ import annotations
import logging
from typing import Any, Sequence
logger = logging.getLogger(__name__)
SOURCE_CALL = 'EXEC dbo.sp_syn_wrt_banhang @start_date = %s, @end_date = %s'
TARGET_SCHEMA = 'dbo'
TARGET_TABLE = 'WRT_SO'
LOG_TABLE = 'WRT_SO_Load_Log'
PENDING_TABLE = 'WRT_SO_Pending'
TERMINAL_STATUSES = {'Delivered', 'Shipped', 'done'}

def _dedupe_columns(columns: Sequence[str]) -> list[str]:
    seen: dict[str, int] = {}
    deduped = []
    for name in columns:
        seen[name] = seen.get(name, 0) + 1
        deduped.append(name if seen[name] == 1 else f'{name}{seen[name]}')
    return deduped

def _fetch_source_rows(source_conn: Any, start_at: str, end_at: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    cursor = source_conn.cursor()
    cursor.execute(SOURCE_CALL, (start_at, end_at))
    columns = _dedupe_columns([desc[0] for desc in cursor.description])
    rows = cursor.fetchall()
    return (columns, [tuple(row) for row in rows])

def _delete_orders(target_conn: Any, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    if not rows:
        return
    code_idx = columns.index('order_number')
    codes = sorted({row[code_idx] for row in rows if row[code_idx]})
    cursor = target_conn.cursor()
    for i in range(0, len(codes), 1000):
        chunk = codes[i:i + 1000]
        placeholders = ', '.join(('%s' for _ in chunk))
        cursor.execute(f'DELETE FROM {TARGET_SCHEMA}.{TARGET_TABLE} WHERE order_number IN ({placeholders})', tuple(chunk))

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
    
    if not rows:
        return
    try:
        code_idx = columns.index('order_number')
        status_idx = columns.index('OrderStatus')
        date_idx = columns.index('postingDate')
    except ValueError:
        logger.warning('Khong tim thay cot order_number/OrderStatus/postingDate trong ket qua nguon - bo qua cap nhat %s.', PENDING_TABLE)
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
        posting_date = latest_date[code]
        posting_date = posting_date.date() if hasattr(posting_date, 'date') else posting_date
        cursor.execute(f'\n            MERGE {TARGET_SCHEMA}.{PENDING_TABLE} AS target\n            USING (SELECT %s AS OrderCode, %s AS PostingDate) AS source\n            ON target.OrderCode = source.OrderCode\n            WHEN MATCHED THEN\n                UPDATE SET LastCheckedAt = SYSUTCDATETIME()\n            WHEN NOT MATCHED THEN\n                INSERT (OrderCode, PostingDate, FirstSeenAt, LastCheckedAt)\n                VALUES (source.OrderCode, source.PostingDate, SYSUTCDATETIME(), SYSUTCDATETIME());\n            ', (code, posting_date))

def _sync_window(source_conn: Any, target_conn: Any, start_at: str, end_at: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    columns, rows = _fetch_source_rows(source_conn, start_at, end_at)
    _delete_orders(target_conn, columns, rows)
    _insert_rows(target_conn, columns, rows)
    return columns, rows

def sync_wrt_sales(source_conn: Any, target_conn: Any, *, start_at: str, end_at: str, **_ignored: Any) -> int:
    try:
        columns, rows = _sync_window(source_conn, target_conn, start_at, end_at)
        _log_window(target_conn, start_at, end_at, len(rows), 'SUCCESS')
        target_conn.commit()
        _sync_pending_table(target_conn, columns, rows)
        target_conn.commit()
    except Exception:
        target_conn.rollback()
        _log_window(target_conn, start_at, end_at, 0, 'FAILED')
        target_conn.commit()
        raise
    logger.info('Da nap %d dong vao %s.%s cho window LastDt %s -> %s', len(rows), TARGET_SCHEMA, TARGET_TABLE, start_at, end_at)
    return len(rows)
