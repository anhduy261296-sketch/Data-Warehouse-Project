from __future__ import annotations
import logging
from typing import Any, Sequence
logger = logging.getLogger(__name__)
SOURCE_CALL = 'EXEC dbo.sp_syn_wrt_banhang @start_date = %s, @end_date = %s'
TARGET_SCHEMA = 'dbo'
TARGET_TABLE = 'WRT_SO'
LOG_TABLE = 'WRT_SO_Load_Log'

def _window_already_loaded(target_conn: Any, start_at: str, end_at: str) -> bool:
    cursor = target_conn.cursor()
    cursor.execute(f"\n        SELECT TOP 1 1\n        FROM {TARGET_SCHEMA}.{LOG_TABLE}\n        WHERE start_at = %s AND end_at = %s AND status = 'SUCCESS'\n        ", (start_at, end_at))
    return cursor.fetchone() is not None

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

def sync_wrt_sales(source_conn: Any, target_conn: Any, *, start_at: str, end_at: str, **_ignored: Any) -> int:
    if _window_already_loaded(target_conn, start_at, end_at):
        logger.info('Window %s -> %s da load roi, bo qua (idempotent).', start_at, end_at)
        return 0
    columns, rows = _fetch_source_rows(source_conn, start_at, end_at)
    try:
        _insert_rows(target_conn, columns, rows)
        _log_window(target_conn, start_at, end_at, len(rows), 'SUCCESS')
        target_conn.commit()
    except Exception:
        target_conn.rollback()
        _log_window(target_conn, start_at, end_at, 0, 'FAILED')
        target_conn.commit()
        raise
    logger.info('Da insert %d dong vao %s.%s cho window %s -> %s', len(rows), TARGET_SCHEMA, TARGET_TABLE, start_at, end_at)
    return len(rows)
