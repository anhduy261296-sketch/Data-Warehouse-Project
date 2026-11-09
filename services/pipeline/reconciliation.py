from __future__ import annotations
import logging
from typing import Any
from services.pipeline.common.constants import TARGET_SCHEMA

logger = logging.getLogger(__name__)
LOG_TABLE = 'RECON_Refresh_Log'
# Cách tính nằm trong view dbo.vw_<tên bảng> (db_migrations), ở đây chỉ khai báo cột cần chép sang bảng.
_TABLES: dict[str, tuple[str, ...]] = {
    'RECON_ECOM': ('OrderCode', 'OmsWmsAmount', 'SapAmount', 'WrtAmount', 'StatusSync', 'SoStatus', 'OrderDate'),
    'RECON_DMS_DUYET': ('OrderCode', 'DmsAmount', 'OmsWmsAmount', 'SapAmount', 'StatusSync', 'SoStatus', 'OrderDate'),
    'RECON_DMS_XUATKHO': ('OrderCode', 'DmsAmount', 'OmsWmsAmount', 'SapAmount', 'WrtAmount', 'StatusSync', 'SoStatus', 'OrderDate'),
    'RECON_WRT': ('OrderCode', 'OmsWmsAmount', 'SapAmount', 'WrtAmount', 'StatusSync', 'SoStatus', 'Type', 'OrderDate'),
}
_BACKUP_TABLES: dict[str, str] = {name: f'{name}_Backup' for name in _TABLES}
STATUS_TRACKING_TABLE = 'STATUS_TRACKING'
RECON_TYPE: dict[str, str] = {'RECON_ECOM': 'ECOM', 'RECON_DMS_DUYET': 'DMS_DUYET', 'RECON_DMS_XUATKHO': 'DMS_XUATKHO', 'RECON_WRT': 'WRT'}
SALEORDERS_TABLE = 'PGI_SaleOrders'
_SALEORDERS_COLUMN_EXPR: dict[str, tuple[str, str, str, str, str]] = {
    'RECON_ECOM': ('NULL', 'OmsWmsAmount', 'SapAmount', 'WrtAmount', 'SoStatus'),
    'RECON_DMS_DUYET': ('DmsAmount', 'OmsWmsAmount', 'SapAmount', 'NULL', 'SoStatus'),
    'RECON_DMS_XUATKHO': ('DmsAmount', 'OmsWmsAmount', 'SapAmount', 'WrtAmount', 'SoStatus'),
    'RECON_WRT': ('NULL', 'OmsWmsAmount', 'SapAmount', 'WrtAmount', 'SoStatus'),
}


def _refresh_table(target_conn: Any, table_name: str) -> int:
    quoted_cols = ', '.join(f'[{c}]' for c in _TABLES[table_name])
    cursor = target_conn.cursor()
    cursor.execute(f'DELETE FROM {TARGET_SCHEMA}.{table_name}')
    cursor.execute(
        f'INSERT INTO {TARGET_SCHEMA}.{table_name} ({quoted_cols}, RefreshedAt) SELECT {quoted_cols}, SYSUTCDATETIME() FROM {TARGET_SCHEMA}.vw_{table_name}'
    )
    cursor.execute(f'SELECT COUNT(*) FROM {TARGET_SCHEMA}.{table_name}')
    return cursor.fetchone()[0]


def _backup_not_synced(target_conn: Any, table_name: str) -> int:
    columns = _TABLES[table_name]
    backup_table = _BACKUP_TABLES[table_name]
    quoted_cols = ', '.join((f'[{c}]' for c in columns)) + ', RefreshedAt, SnapshotAt'
    select_cols = ', '.join((f'[{c}]' for c in columns)) + ', RefreshedAt, SYSUTCDATETIME()'
    cursor = target_conn.cursor()
    cursor.execute(
        f"\n        INSERT INTO {TARGET_SCHEMA}.{backup_table} ({quoted_cols})\n        SELECT {select_cols}\n        FROM {TARGET_SCHEMA}.{table_name}\n        WHERE StatusSync = 'Not Sync'\n        "
    )
    cursor.execute('SELECT @@ROWCOUNT')
    return cursor.fetchone()[0]


def _sync_to_saleorders(target_conn: Any, table_name: str) -> None:
    dms_expr, oms_expr, sap_expr, wrt_expr, status_expr = _SALEORDERS_COLUMN_EXPR[table_name]
    merge_sql = f"\n        MERGE {TARGET_SCHEMA}.{SALEORDERS_TABLE} AS target\n        USING (\n            SELECT\n                OrderCode,\n                {dms_expr} AS DmsAmount,\n                {oms_expr} AS OmsWmsAmount,\n                {sap_expr} AS SapAmount,\n                {wrt_expr} AS WrtAmount,\n                {status_expr} AS SoStatus,\n                SYSUTCDATETIME() AS SyncedAt\n            FROM {TARGET_SCHEMA}.{table_name}\n            WHERE StatusSync = 'Sync'\n        ) AS source\n        ON target.OrderCode = source.OrderCode AND target.SourceTable = '{table_name}'\n        WHEN MATCHED THEN\n            UPDATE SET\n                DmsAmount = source.DmsAmount, OmsWmsAmount = source.OmsWmsAmount,\n                SapAmount = source.SapAmount, WrtAmount = source.WrtAmount,\n                SoStatus = source.SoStatus, SyncedAt = source.SyncedAt\n        WHEN NOT MATCHED BY TARGET THEN\n            INSERT (OrderCode, SourceTable, DmsAmount, OmsWmsAmount, SapAmount, WrtAmount, SoStatus, SyncedAt)\n            VALUES (source.OrderCode, '{table_name}', source.DmsAmount, source.OmsWmsAmount,\n                    source.SapAmount, source.WrtAmount, source.SoStatus, source.SyncedAt)\n        WHEN NOT MATCHED BY SOURCE AND target.SourceTable = '{table_name}' THEN\n            DELETE;\n    "
    cursor = target_conn.cursor()
    cursor.execute(merge_sql)


def _sync_status_tracking(target_conn: Any, table_name: str) -> None:
    recon_type = RECON_TYPE[table_name]
    cursor = target_conn.cursor()
    cursor.execute(
        f"\n        MERGE {TARGET_SCHEMA}.{STATUS_TRACKING_TABLE} AS target\n        USING (\n            SELECT OrderCode AS BusinessKey, StatusSync\n            FROM {TARGET_SCHEMA}.{table_name}\n        ) AS source\n        ON target.ReconType = '{recon_type}' AND target.BusinessKey = source.BusinessKey\n        WHEN MATCHED THEN\n            UPDATE SET\n                StatusSync = source.StatusSync,\n                UpdatedAt = SYSUTCDATETIME(),\n                SyncAt = CASE\n                    WHEN source.StatusSync = 'Sync' AND target.StatusSync <> 'Sync' THEN SYSUTCDATETIME()\n                    ELSE target.SyncAt\n                END\n        WHEN NOT MATCHED BY TARGET THEN\n            INSERT (ReconType, BusinessKey, StatusSync, CreatedAt, UpdatedAt, SyncAt)\n            VALUES (\n                '{recon_type}', source.BusinessKey, source.StatusSync,\n                SYSUTCDATETIME(), SYSUTCDATETIME(),\n                CASE WHEN source.StatusSync = 'Sync' THEN SYSUTCDATETIME() ELSE NULL END\n            )\n        WHEN NOT MATCHED BY SOURCE AND target.ReconType = '{recon_type}' THEN\n            DELETE;\n        "
    )


def _log_refresh(target_conn: Any, table_name: str, row_count: int, status: str) -> None:
    cursor = target_conn.cursor()
    cursor.execute(
        f'\n        INSERT INTO {TARGET_SCHEMA}.{LOG_TABLE} (table_name, row_count, status, refreshed_at)\n        VALUES (%s, %s, %s, SYSUTCDATETIME())\n        ',
        (table_name, row_count, status),
    )


INVENTORY_TABLE = 'RECON_INVENTORY'
_INVENTORY_COLUMNS = ('StatusSync', 'ItemCode', 'ItemName', 'WhsCode', 'WhsName', 'StatusItem', 'SapQty', 'WmsQty', 'DiffQty', 'InvntryUom')


def refresh_inventory_reconciliation(target_conn: Any, **_ignored: Any) -> int:
    cursor = target_conn.cursor()
    try:
        cursor.execute(f'DELETE FROM {TARGET_SCHEMA}.{INVENTORY_TABLE}')
        columns = ', '.join(f'[{c}]' for c in _INVENTORY_COLUMNS)
        cursor.execute(f'INSERT INTO {TARGET_SCHEMA}.{INVENTORY_TABLE} ({columns}) SELECT {columns} FROM {TARGET_SCHEMA}.vw_{INVENTORY_TABLE}')
        cursor.execute(f'SELECT COUNT(*) FROM {TARGET_SCHEMA}.{INVENTORY_TABLE}')
        row_count = cursor.fetchone()[0]
        _log_refresh(target_conn, INVENTORY_TABLE, row_count, 'SUCCESS')
        target_conn.commit()
    except Exception:
        target_conn.rollback()
        _log_refresh(target_conn, INVENTORY_TABLE, 0, 'FAILED')
        target_conn.commit()
        logger.exception('Refresh %s that bai', INVENTORY_TABLE)
        raise
    logger.info('Da refresh %s: %d dong', INVENTORY_TABLE, row_count)
    return row_count


def refresh_all_reconciliation_tables(target_conn: Any, **_ignored: Any) -> dict[str, int]:
    results: dict[str, int] = {}
    for table_name in _TABLES:
        try:
            row_count = _refresh_table(target_conn, table_name)
            _log_refresh(target_conn, table_name, row_count, 'SUCCESS')
            target_conn.commit()
            results[table_name] = row_count
            logger.info('Da refresh %s: %d dong', table_name, row_count)
            backup_count = _backup_not_synced(target_conn, table_name)
            _sync_to_saleorders(target_conn, table_name)
            _sync_status_tracking(target_conn, table_name)
            target_conn.commit()
            logger.info('Da backup %d dong Not Sync va sync vao %s cho %s', backup_count, SALEORDERS_TABLE, table_name)
        except Exception:
            target_conn.rollback()
            _log_refresh(target_conn, table_name, 0, 'FAILED')
            target_conn.commit()
            logger.exception('Refresh %s that bai', table_name)
            results[table_name] = -1
    failed = [name for name, count in results.items() if count < 0]
    if failed:
        raise RuntimeError(f"Refresh that bai cho: {', '.join(failed)} (xem log/{LOG_TABLE})")
    return results
