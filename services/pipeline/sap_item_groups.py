from __future__ import annotations
import logging
from typing import Any
logger = logging.getLogger(__name__)
SOURCE_QUERY = 'SELECT "ItmsGrpCod", "ItmsGrpNam" FROM "PGI_GOLIVE"."OITB"'
TARGET_SCHEMA = 'dbo'
TARGET_TABLE = 'SAP_ITEM_GROUPS'

def sync_sap_item_groups(source_conn: Any, target_conn: Any, **_ignored: Any) -> int:
    cursor = source_conn.cursor()
    cursor.execute(SOURCE_QUERY)
    rows = [(str(code), name) for code, name in cursor.fetchall() if code is not None]
    if not rows:
        raise RuntimeError('OITB khong tra ve nhom hang nao - khong ghi de SAP_ITEM_GROUPS.')
    target = target_conn.cursor()
    try:
        target.execute(f'DELETE FROM {TARGET_SCHEMA}.{TARGET_TABLE}')
        target.executemany(f'INSERT INTO {TARGET_SCHEMA}.{TARGET_TABLE} (ItmsGrpCod, ItmsGrpNam, LoadedAt) VALUES (%s, %s, SYSUTCDATETIME())', rows)
        target_conn.commit()
    except Exception:
        target_conn.rollback()
        raise
    logger.info('Da dong bo %d nhom hang (OITB) vao %s.%s', len(rows), TARGET_SCHEMA, TARGET_TABLE)
    return len(rows)
UOM_SOURCE_QUERY = 'SELECT "UomCode", "UomName" FROM "PGI_GOLIVE"."OUOM" WHERE "UomEntry" > 0'
UOM_TABLE = 'SAP_UOM'

def sync_sap_uoms(source_conn: Any, target_conn: Any, **_ignored: Any) -> int:
    cursor = source_conn.cursor()
    cursor.execute(UOM_SOURCE_QUERY)
    rows = [(code, name) for code, name in cursor.fetchall() if code]
    if not rows:
        raise RuntimeError('OUOM khong tra ve don vi tinh nao - khong ghi de SAP_UOM.')
    target = target_conn.cursor()
    try:
        target.execute(f'DELETE FROM {TARGET_SCHEMA}.{UOM_TABLE}')
        target.executemany(f'INSERT INTO {TARGET_SCHEMA}.{UOM_TABLE} (UomCode, UomName, LoadedAt) VALUES (%s, %s, SYSUTCDATETIME())', rows)
        target_conn.commit()
    except Exception:
        target_conn.rollback()
        raise
    logger.info('Da dong bo %d don vi tinh (OUOM) vao %s.%s', len(rows), TARGET_SCHEMA, UOM_TABLE)
    return len(rows)
