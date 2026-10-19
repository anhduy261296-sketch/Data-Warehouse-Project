from __future__ import annotations

from typing import Any, Iterable

from .constants import TARGET_SCHEMA


def assert_tables_exist(
    target_conn: Any, tables: Iterable[str], hint: str = 'chay db_migrations truoc.', schema: str = TARGET_SCHEMA
) -> None:
    cursor = target_conn.cursor()
    for table in tables:
        cursor.execute("SELECT OBJECT_ID(%s, 'U')", (f'{schema}.{table}',))
        if cursor.fetchone()[0] is None:
            raise RuntimeError(f'Bang {schema}.{table} chua ton tai - {hint}')


def enable_fast_executemany(cursor: Any) -> None:
    for target in (cursor, getattr(cursor, 'cursor', None)):
        if target is None:
            continue
        try:
            target.fast_executemany = True
        except Exception:
            pass
