from __future__ import annotations
import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Sequence
logger = logging.getLogger(__name__)
SOURCE_CALL = 'CALL "PGI_GOLIVE"."BTS_RPT_R502_KT"(?, ?, ?)'
REPORT_TYPE = '2'
START_DATE = '2026-06-28'
TARGET_SCHEMA = 'dbo'
TARGET_TABLE = 'SAP_INVENTORY'
STAGING_TABLE = 'SAP_INVENTORY_Staging'
LOG_TABLE = 'SAP_INVENTORY_Load_Log'
MIN_ROW_RATIO = 0.9
MAX_SQL_PARAMS = 2090
COLUMNS = ('LoaiCT', 'TenLoaiCT', 'SoCT', 'DocDate', 'SlpName', 'BoPhan', 'CreatedBy', 'SoCT_NhapXuat', 'DocDate_NhapXuat', 'DocType', 'DocEntry', 'DocLineNum', 'BaseType', 'BaseEntry', 'BaseLine', 'IN_WhsCode', 'IN_WhsName', 'IN_BinCode', 'OUT_WhsCode', 'OUT_WhsName', 'OUT_BinCode', 'U_ItemProducer', 'NSX', 'ItmsGrpCod', 'ItmsGrpNam', 'ItemCode', 'U_PGICode', 'ItemName', 'InvntryUom', 'DistNumber', 'InStock', 'Cost', 'TransValue', 'Comments', 'CardCode', 'CardName', 'U_IMNo')
COST_QUANTUM = Decimal('1e-18')

def _fetch_rows(source_conn: Any, start_date: str, end_date: str) -> list[tuple[Any, ...]]:
    cursor = source_conn.cursor()
    cursor.execute(SOURCE_CALL, (start_date, end_date, REPORT_TYPE))
    columns = tuple((desc[0] for desc in cursor.description))
    if columns != COLUMNS:
        raise RuntimeError(f'Cot tra ve tu {SOURCE_CALL} khac voi bang {TARGET_TABLE} - kiem tra lai procedure. Nhan duoc: {columns}')
    cost_idx = COLUMNS.index('Cost')
    rows = []
    for row in cursor.fetchall():
        row = list(row)
        if isinstance(row[cost_idx], Decimal):
            row[cost_idx] = row[cost_idx].quantize(COST_QUANTUM, rounding=ROUND_HALF_UP)
        rows.append(tuple(row))
    return rows

def _count(target_conn: Any, table: str) -> int:
    cursor = target_conn.cursor()
    cursor.execute(f'SELECT COUNT(*) FROM {TARGET_SCHEMA}.{table}')
    return cursor.fetchone()[0]

def _load_staging(target_conn: Any, rows: Sequence[Sequence[Any]]) -> None:
    cursor = target_conn.cursor()
    cursor.execute(f'DELETE FROM {TARGET_SCHEMA}.{STAGING_TABLE}')
    quoted_cols = ', '.join((f'[{c}]' for c in COLUMNS))
    row_placeholder = '(' + ', '.join(('%s' for _ in COLUMNS)) + ')'
    batch_size = MAX_SQL_PARAMS // len(COLUMNS)
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        values_sql = ', '.join((row_placeholder for _ in batch))
        params = tuple((value for row in batch for value in row))
        cursor.execute(f'INSERT INTO {TARGET_SCHEMA}.{STAGING_TABLE} ({quoted_cols}) VALUES {values_sql}', params)
    target_conn.commit()

def _replace_target_from_staging(target_conn: Any) -> None:
    quoted_cols = ', '.join((f'[{c}]' for c in COLUMNS))
    cursor = target_conn.cursor()
    cursor.execute(f'DELETE FROM {TARGET_SCHEMA}.{TARGET_TABLE}')
    cursor.execute(f'INSERT INTO {TARGET_SCHEMA}.{TARGET_TABLE} ({quoted_cols}) SELECT {quoted_cols} FROM {TARGET_SCHEMA}.{STAGING_TABLE}')
    target_conn.commit()

def _log(target_conn: Any, start_date: str, end_date: str, row_count: int, status: str, message: str | None=None) -> None:
    cursor = target_conn.cursor()
    cursor.execute(f'INSERT INTO {TARGET_SCHEMA}.{LOG_TABLE} (start_at, end_at, row_count, status, message) VALUES (%s, %s, %s, %s, %s)', (start_date, end_date, row_count, status, message))
    target_conn.commit()

def sync_sap_inventory(source_conn: Any, target_conn: Any, *, end_date: str, start_date: str=START_DATE, force: bool=False, **_ignored: Any) -> int:
    try:
        rows = _fetch_rows(source_conn, start_date, end_date)
        _load_staging(target_conn, rows)
        staged = _count(target_conn, STAGING_TABLE)
        if staged == 0:
            raise RuntimeError('SAP tra ve 0 dong - nghi nguon loi, giu nguyen bang chinh.')
        current = _count(target_conn, TARGET_TABLE)
        if not force and current and staged < current * MIN_ROW_RATIO:
            raise RuntimeError(f'So dong moi ({staged}) giam qua {round((1 - MIN_ROW_RATIO) * 100)}% so voi hien tai ({current}) - nghi nguon loi, giu nguyen bang chinh. Chay lai voi force=True neu chac chan dung.')
        _replace_target_from_staging(target_conn)
    except Exception as exc:
        target_conn.rollback()
        _log(target_conn, start_date, end_date, 0, 'FAILED', str(exc)[:1000])
        raise
    _log(target_conn, start_date, end_date, staged, 'SUCCESS')
    logger.info('Da nap %d dong vao %s.%s (%s -> %s)', staged, TARGET_SCHEMA, TARGET_TABLE, start_date, end_date)
    return staged
