from __future__ import annotations

import re
from typing import Any

from .values import TEXT_MAX_LEN

COLUMN_TYPES = {'text': f'NVARCHAR({TEXT_MAX_LEN})', 'number': 'DECIMAL(18, 2)', 'date': 'DATE', 'datetime': 'DATETIME2(0)'}
NAME_RE = re.compile(r'^[a-z][a-z0-9_]{0,49}$')
SYSTEM_COLUMNS = frozenset({'id', 'batchid', 'recipientid', 'phone', 'createdat'})


def validate_name(name: str) -> str | None:
    if not NAME_RE.match(name or ''):
        return 'Tên biến chỉ gồm chữ thường không dấu, số, dấu _ và bắt đầu bằng chữ (tối đa 50 ký tự)'
    if name.replace('_', '') in SYSTEM_COLUMNS:
        return f'"{name}" là tên cột hệ thống, hãy đặt tên khác'
    return None


def data_table(template_id: int) -> str:
    return f'ZnsData_{int(template_id)}'


def _column(name: str) -> str:
    if validate_name(name):
        raise ValueError(f'Tên cột không hợp lệ: {name}')
    return f'[{name}]'


def create_data_table(cursor: Any, template_id: int, variables: list[dict]) -> str:
    table = data_table(template_id)
    columns = ''.join(f',\n    {_column(v["name"])} {COLUMN_TYPES[v["data_type"]]} NULL' for v in variables)
    cursor.execute(
        f"""
        CREATE TABLE dbo.[{table}] (
            Id BIGINT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_{table} PRIMARY KEY,
            BatchId INT NOT NULL,
            RecipientId BIGINT NOT NULL,
            Phone VARCHAR(20) NOT NULL,
            CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_{table}_CreatedAt DEFAULT SYSUTCDATETIME(){columns}
        )
        """
    )
    cursor.execute(f'CREATE INDEX IX_{table}_Batch ON dbo.[{table}] (BatchId)')
    return table


def add_column(cursor: Any, table: str, name: str, data_type: str) -> None:
    cursor.execute(f'ALTER TABLE dbo.[{table}] ADD {_column(name)} {COLUMN_TYPES[data_type]} NULL')


def drop_column(cursor: Any, table: str, name: str) -> None:
    cursor.execute(f'ALTER TABLE dbo.[{table}] DROP COLUMN {_column(name)}')


def change_column_type(cursor: Any, table: str, name: str, data_type: str) -> None:
    cursor.execute(f'ALTER TABLE dbo.[{table}] ALTER COLUMN {_column(name)} {COLUMN_TYPES[data_type]} NULL')


def columns_with_data(cursor: Any, table: str, names: list[str]) -> set[str]:
    if not names:
        return set()
    checks = ', '.join(f'MAX(CASE WHEN {_column(n)} IS NOT NULL THEN 1 ELSE 0 END)' for n in names)
    cursor.execute(f'SELECT {checks} FROM dbo.[{table}]')
    row = cursor.fetchone() or ()
    return {n for n, flag in zip(names, row) if flag}
