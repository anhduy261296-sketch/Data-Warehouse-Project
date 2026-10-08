from __future__ import annotations
import logging
from collections import defaultdict
from decimal import Decimal
from typing import Any, Sequence
logger = logging.getLogger(__name__)
WAREHOUSE_QUERY = '\nSELECT w."ItemCode", i."ItemName", w."WhsCode", h."WhsName", w."OnHand", i."InvntryUom"\nFROM "PGI_GOLIVE"."OITW" w\nJOIN "PGI_GOLIVE"."OITM" i ON i."ItemCode" = w."ItemCode"\nJOIN "PGI_GOLIVE"."OWHS" h ON h."WhsCode" = w."WhsCode"\nWHERE w."OnHand" <> 0\n'
BIN_QUERY = '\nSELECT q."ItemCode", q."WhsCode", b."BinCode", q."OnHandQty"\nFROM "PGI_GOLIVE"."OIBQ" q\nJOIN "PGI_GOLIVE"."OBIN" b ON b."AbsEntry" = q."BinAbs"\nWHERE q."OnHandQty" <> 0\n'
TARGET_SCHEMA = 'dbo'
TARGET_TABLE = 'SAP_INVENTORY'
STAGING_TABLE = 'SAP_INVENTORY_Staging'
LOG_TABLE = 'SAP_INVENTORY_Load_Log'
MIN_ROW_RATIO = 0.9
MAX_SQL_PARAMS = 2090
COLUMNS = ('ItemCode', 'ItemName', 'WhsCode', 'WhsName', 'StatusItem', 'OnHand', 'InvntryUom')

def status_item_from_bin(bin_code: str | None) -> str:
    if not bin_code:
        return ''
    return bin_code.rsplit('-', 1)[-1]

def _fetch_rows(source_conn: Any) -> list[tuple[Any, ...]]:
    cursor = source_conn.cursor()
    cursor.execute(WAREHOUSE_QUERY)
    warehouse_rows = cursor.fetchall()
    cursor.execute(BIN_QUERY)
    bin_qty: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for item_code, whs_code, bin_code, qty in cursor.fetchall():
        bin_qty[item_code, whs_code][status_item_from_bin(bin_code)] += Decimal(qty)
    rows = []
    for item_code, item_name, whs_code, whs_name, on_hand, uom in warehouse_rows:
        by_status = bin_qty.get((item_code, whs_code), {})
        for status_item, qty in by_status.items():
            if qty:
                rows.append((item_code, item_name, whs_code, whs_name, status_item, qty, uom))
        remainder = Decimal(on_hand) - sum(by_status.values(), Decimal(0))
        if remainder:
            rows.append((item_code, item_name, whs_code, whs_name, '', remainder, uom))
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

def _log(target_conn: Any, row_count: int, status: str, message: str | None=None) -> None:
    cursor = target_conn.cursor()
    cursor.execute(f'INSERT INTO {TARGET_SCHEMA}.{LOG_TABLE} (row_count, status, message) VALUES (%s, %s, %s)', (row_count, status, message))
    target_conn.commit()

def sync_sap_inventory(source_conn: Any, target_conn: Any, *, force: bool=False, **_ignored: Any) -> int:
    try:
        rows = _fetch_rows(source_conn)
        _load_staging(target_conn, rows)
        staged = _count(target_conn, STAGING_TABLE)
        if staged == 0:
            raise RuntimeError('SAP tra ve 0 dong ton kho - nghi nguon loi, giu nguyen bang chinh.')
        current = _count(target_conn, TARGET_TABLE)
        if not force and current and staged < current * MIN_ROW_RATIO:
            raise RuntimeError(f'So dong moi ({staged}) giam qua {round((1 - MIN_ROW_RATIO) * 100)}% so voi hien tai ({current}) - nghi nguon loi, giu nguyen bang chinh. Chay lai voi force=True neu chac chan dung.')
        _replace_target_from_staging(target_conn)
    except Exception as exc:
        target_conn.rollback()
        _log(target_conn, 0, 'FAILED', str(exc)[:1000])
        raise
    _log(target_conn, staged, 'SUCCESS')
    logger.info('Da nap %d dong ton kho vao %s.%s', staged, TARGET_SCHEMA, TARGET_TABLE)
    return staged
