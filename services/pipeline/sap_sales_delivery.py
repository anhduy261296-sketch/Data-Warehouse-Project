from __future__ import annotations
import logging
from typing import Any, Sequence
logger = logging.getLogger(__name__)
SOURCE_CALL = 'CALL "PGI_GOLIVE"."SP_SYN_SALES_DELIVERY_AR"(TO_DATE(?, \'YYYY-MM-DD\'), TO_DATE(?, \'YYYY-MM-DD\'))'
TARGET_SCHEMA = 'dbo'
STAGING_TABLE = 'SAP_SO'
FINAL_TABLE = 'SAP_SO_All'
LOG_TABLE = 'SAP_SO_Load_Log'
PENDING_TABLE = 'SAP_SO_Pending'
MERGE_KEY_COLUMNS = ('U_SONo', 'ItemCode', 'Type')
DOC_DATE_COLUMN = 'DocDate'
PENDING_AR_COLUMN = 'ARDocDate'
AMOUNT_TIEBREAK_COLUMN = 'TotalAfVAT'

def _fetch_day(source_conn: Any, day: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    cursor = source_conn.cursor()
    cursor.execute(SOURCE_CALL, (day, day))
    columns = [desc[0] for desc in cursor.description]
    rows = [tuple(row) for row in cursor.fetchall()]
    return (columns, rows)

def _truncate_staging(target_conn: Any) -> None:
    cursor = target_conn.cursor()
    cursor.execute(f'DELETE FROM {TARGET_SCHEMA}.{STAGING_TABLE}')

def _insert_into_staging(target_conn: Any, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    if not rows:
        return
    quoted_cols = ', '.join((f'[{c}]' for c in columns))
    placeholders = ', '.join(('%s' for _ in columns))
    insert_sql = f'INSERT INTO {TARGET_SCHEMA}.{STAGING_TABLE} ({quoted_cols}) VALUES ({placeholders})'
    cursor = target_conn.cursor()
    if hasattr(cursor, 'fast_executemany'):
        cursor.fast_executemany = True
    cursor.executemany(insert_sql, list(rows))

def _merge_staging_into_final(target_conn: Any, columns: Sequence[str]) -> None:
    non_key_columns = [c for c in columns if c not in MERGE_KEY_COLUMNS]
    on_clause = ' AND '.join((f'target.[{c}] = source.[{c}]' for c in MERGE_KEY_COLUMNS))
    set_clause = ', '.join((f'target.[{c}] = source.[{c}]' for c in non_key_columns))
    insert_cols = ', '.join((f'[{c}]' for c in columns))
    insert_values = ', '.join((f'source.[{c}]' for c in columns))
    all_cols = ', '.join((f'[{c}]' for c in columns))
    partition_cols = ', '.join((f'[{c}]' for c in MERGE_KEY_COLUMNS))
    merge_sql = f'\n        MERGE {TARGET_SCHEMA}.{FINAL_TABLE} AS target\n        USING (\n            SELECT {all_cols}\n            FROM (\n                SELECT {all_cols},\n                       ROW_NUMBER() OVER (\n                           PARTITION BY {partition_cols}\n                           ORDER BY CASE WHEN [{PENDING_AR_COLUMN}] IS NOT NULL THEN 0 ELSE 1 END,\n                                    CASE WHEN TRY_CONVERT(DECIMAL(18,2), [{AMOUNT_TIEBREAK_COLUMN}]) <> 0 THEN 0 ELSE 1 END\n                       ) AS _rn\n                FROM {TARGET_SCHEMA}.{STAGING_TABLE}\n            ) _deduped\n            WHERE _rn = 1\n        ) AS source\n        ON {on_clause}\n        WHEN MATCHED THEN\n            UPDATE SET {set_clause}\n        WHEN NOT MATCHED THEN\n            INSERT ({insert_cols}) VALUES ({insert_values});\n    '
    cursor = target_conn.cursor()
    cursor.execute(merge_sql)

def _get_pending_dates(target_conn: Any, before_date: str) -> list[str]:
    cursor = target_conn.cursor()
    cursor.execute(f'SELECT DISTINCT {DOC_DATE_COLUMN} FROM {TARGET_SCHEMA}.{PENDING_TABLE} WHERE {DOC_DATE_COLUMN} < %s ORDER BY {DOC_DATE_COLUMN}', (before_date,))
    result = []
    for d, in cursor.fetchall():
        result.append(d.isoformat() if hasattr(d, 'isoformat') else str(d)[:10])
    return result

def _sync_pending_table(target_conn: Any) -> None:
    cursor = target_conn.cursor()
    cursor.execute(f'\n        DELETE p\n        FROM {TARGET_SCHEMA}.{PENDING_TABLE} p\n        INNER JOIN {TARGET_SCHEMA}.{STAGING_TABLE} s\n            ON s.U_SONo = p.U_SONo AND s.ItemCode = p.ItemCode AND s.Type = p.Type\n        WHERE s.{PENDING_AR_COLUMN} IS NOT NULL\n        ')
    cursor.execute(f'\n        INSERT INTO {TARGET_SCHEMA}.{PENDING_TABLE} (U_SONo, ItemCode, Type, DocDate, FirstSeenAt)\n        SELECT DISTINCT s.U_SONo, s.ItemCode, s.Type, CAST(s.{DOC_DATE_COLUMN} AS DATE), SYSUTCDATETIME()\n        FROM {TARGET_SCHEMA}.{STAGING_TABLE} s\n        WHERE s.{PENDING_AR_COLUMN} IS NULL\n          AND NOT EXISTS (\n              SELECT 1 FROM {TARGET_SCHEMA}.{PENDING_TABLE} p\n              WHERE p.U_SONo = s.U_SONo AND p.ItemCode = s.ItemCode AND p.Type = s.Type\n          )\n        ')

def _log_action(target_conn: Any, start_at: str, end_at: str, row_count: int, action: str, status: str) -> None:
    cursor = target_conn.cursor()
    cursor.execute(f'\n        INSERT INTO {TARGET_SCHEMA}.{LOG_TABLE} (start_at, end_at, row_count, action, status, loaded_at)\n        VALUES (%s, %s, %s, %s, %s, SYSUTCDATETIME())\n        ', (start_at, end_at, row_count, action, status))

def sync_sap_sales_delivery(source_conn: Any, target_conn: Any, *, process_date: str, **_ignored: Any) -> int:
    _truncate_staging(target_conn)
    target_conn.commit()
    full_row_count = 0
    repull_row_count = 0
    try:
        columns, full_rows = _fetch_day(source_conn, process_date)
        full_row_count = len(full_rows)
        _insert_into_staging(target_conn, columns, full_rows)
        target_conn.commit()
        _log_action(target_conn, process_date, process_date, full_row_count, 'insert', 'SUCCESS')
        target_conn.commit()
        pending_dates = _get_pending_dates(target_conn, process_date)
        if pending_dates:
            repull_rows: list[tuple[Any, ...]] = []
            for day in pending_dates:
                _, day_rows = _fetch_day(source_conn, day)
                repull_rows.extend(day_rows)
            repull_row_count = len(repull_rows)
            _insert_into_staging(target_conn, columns, repull_rows)
            target_conn.commit()
            _log_action(target_conn, pending_dates[0], pending_dates[-1], repull_row_count, 'update', 'SUCCESS')
            target_conn.commit()
        _merge_staging_into_final(target_conn, columns)
        target_conn.commit()
        _sync_pending_table(target_conn)
        target_conn.commit()
    except Exception:
        target_conn.rollback()
        _log_action(target_conn, process_date, process_date, 0, 'insert', 'FAILED')
        target_conn.commit()
        raise
    finally:
        _truncate_staging(target_conn)
        target_conn.commit()
    total = full_row_count + repull_row_count
    logger.info('Da merge %d dong (full=%d, repull=%d) vao %s.%s cho ngay %s', total, full_row_count, repull_row_count, TARGET_SCHEMA, FINAL_TABLE, process_date)
    return total
