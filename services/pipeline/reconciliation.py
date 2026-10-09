from __future__ import annotations
import logging
from typing import Any
logger = logging.getLogger(__name__)
TARGET_SCHEMA = 'dbo'
LOG_TABLE = 'RECON_Refresh_Log'
_ECOM_ORDER_FILTER = "outbound_order_type IN ('L03', 'L04')"
_DMS_XUATKHO_ORDER_FILTER = "outbound_order_type IN ('L01', 'L05', 'L07', 'L08', 'L12', 'L14', 'L18', 'L25')"
_WRT_ORDER_FILTER = "IsCreateBy = 'SYSTEM'"
_ECOM_OMS_SALES_FILTER = "order_type = 'Sales'"
_ECOM_SAP_TYPE_FILTER = "[Type] = N'Bán hàng'"
_OMS_SHIPPED_STATUSES = "('Shipped', 'Delivered')"
_WRT_SHIPPED_STATUS = "('Shipped', 'Delivered', 'done')"
_ECOM_SQL = f"\nWITH OMS AS (\n    SELECT order_number, MAX(status) AS SoStatus,\n           SUM(TRY_CONVERT(DECIMAL(18,0), total_amount_after_vat)) AS TotalAmt,\n           MAX(TRY_CONVERT(DATETIME2, created_date)) AS OrderDate\n    FROM dbo.OMS_ORDERS\n    WHERE {_ECOM_ORDER_FILTER} AND {_ECOM_OMS_SALES_FILTER}\n    GROUP BY order_number\n),\nSAP_LINES AS (\n    SELECT U_SONo, ItemCode, ARNo,\n           CASE WHEN ARNo IS NOT NULL AND ARNo <> ''\n                THEN MAX(TRY_CONVERT(DECIMAL(18,0), ARGTotal))\n                ELSE SUM(TRY_CONVERT(DECIMAL(18,0), TotalAfVAT))\n           END AS ItemAmt\n    FROM dbo.SAP_SO_All\n    WHERE {_ECOM_SAP_TYPE_FILTER}\n    GROUP BY U_SONo, ItemCode, ARNo\n),\nSAP AS (\n    SELECT U_SONo, SUM(ItemAmt) AS TotalAmt\n    FROM SAP_LINES\n    GROUP BY U_SONo\n),\nWRT AS (\n    SELECT order_number, SUM(TRY_CONVERT(DECIMAL(18,0), TotalAmt)) AS TotalAmt\n    FROM dbo.WRT_SO\n    GROUP BY order_number\n)\n%%INSERT%%\nSELECT\n    o.order_number AS OrderCode,\n    o.TotalAmt AS OmsWmsAmount,\n    s.TotalAmt AS SapAmount,\n    CAST(w.TotalAmt AS DECIMAL(18,0)) AS WrtAmount,\n    CASE\n        WHEN o.order_number IS NOT NULL AND s.U_SONo IS NOT NULL AND w.order_number IS NOT NULL\n         AND o.TotalAmt = s.TotalAmt AND s.TotalAmt = CAST(w.TotalAmt AS DECIMAL(18,0))\n         AND o.SoStatus IN {_OMS_SHIPPED_STATUSES}\n        THEN 'Sync' ELSE 'Not Sync'\n    END AS StatusSync,\n    o.SoStatus,\n    o.OrderDate,\n    SYSUTCDATETIME()\nFROM OMS o\nLEFT JOIN SAP s ON s.U_SONo = o.order_number\nLEFT JOIN WRT w ON w.order_number = o.order_number;\n"
_DMS_DUYET_SQL = f"\nWITH DMS AS (\n    SELECT OrderCode, MAX(OrderStatus) AS OrderStatus,\n           SUM(CASE WHEN OrderType = 'L14' THEN -TotalAmtInclVAT ELSE TotalAmtInclVAT END) AS TotalAmt,\n           MAX(DocDate) AS OrderDate\n    FROM dbo.DMS_SO\n    WHERE OrderStatus = 'sale'\n    GROUP BY OrderCode\n),\nOMS AS (\n    SELECT order_number,\n           SUM(TRY_CONVERT(DECIMAL(18,2), total_amount_after_vat)) AS TotalAmt\n    FROM dbo.OMS_ORDERS\n    GROUP BY order_number\n),\nSAP_LINES AS (\n    SELECT U_SONo, ItemCode, ARNo,\n           CASE WHEN ARNo IS NOT NULL AND ARNo <> ''\n                THEN MAX(TRY_CONVERT(DECIMAL(18,2), ARGTotal))\n                ELSE SUM(TRY_CONVERT(DECIMAL(18,2), TotalAfVAT))\n           END AS ItemAmt\n    FROM dbo.SAP_SO_All\n    GROUP BY U_SONo, ItemCode, ARNo\n),\nSAP AS (\n    SELECT U_SONo, SUM(ItemAmt) AS TotalAmt\n    FROM SAP_LINES\n    GROUP BY U_SONo\n)\n%%INSERT%%\nSELECT\n    d.OrderCode,\n    CAST(d.TotalAmt AS DECIMAL(18,2)) AS DmsAmount,\n    o.TotalAmt AS OmsWmsAmount,\n    s.TotalAmt AS SapAmount,\n    CASE\n        WHEN o.order_number IS NOT NULL AND s.U_SONo IS NOT NULL\n         AND CAST(d.TotalAmt AS DECIMAL(18,2)) = o.TotalAmt AND o.TotalAmt = s.TotalAmt\n        THEN 'Sync' ELSE 'Not Sync'\n    END AS StatusSync,\n    d.OrderStatus AS SoStatus,\n    d.OrderDate,\n    SYSUTCDATETIME()\nFROM DMS d\nLEFT JOIN OMS o ON o.order_number = d.OrderCode\nLEFT JOIN SAP s ON s.U_SONo = d.OrderCode;\n"
_DMS_XUATKHO_SQL = f"\nWITH DMS_DONE AS (\n    SELECT OrderCode, MAX(OrderStatus) AS OrderStatus,\n           SUM(CASE WHEN OrderType = 'L14' THEN -TotalAmtInclVAT ELSE TotalAmtInclVAT END) AS TotalAmt\n    FROM dbo.DMS_SO\n    GROUP BY OrderCode\n),\nOMS AS (\n    SELECT order_number, SUM(TRY_CONVERT(DECIMAL(18,2), total_amount_after_vat)) AS TotalAmt,\n           MAX(TRY_CONVERT(DATETIME2, created_date)) AS OrderDate\n    FROM dbo.OMS_ORDERS\n    WHERE {_DMS_XUATKHO_ORDER_FILTER}\n    GROUP BY order_number\n),\nSAP_LINES AS (\n    SELECT U_SONo, ItemCode, ARNo,\n           CASE WHEN ARNo IS NOT NULL AND ARNo <> ''\n                THEN MAX(TRY_CONVERT(DECIMAL(18,2), ARGTotal))\n                ELSE SUM(TRY_CONVERT(DECIMAL(18,2), TotalAfVAT))\n           END AS ItemAmt\n    FROM dbo.SAP_SO_All\n    GROUP BY U_SONo, ItemCode, ARNo\n),\nSAP AS (\n    SELECT U_SONo, SUM(ItemAmt) AS TotalAmt\n    FROM SAP_LINES\n    GROUP BY U_SONo\n),\nWRT AS (\n    SELECT order_number, SUM(TRY_CONVERT(DECIMAL(18,4), TotalAmt)) AS TotalAmt\n    FROM dbo.WRT_SO\n    GROUP BY order_number\n)\n%%INSERT%%\nSELECT\n    o.order_number AS OrderCode,\n    CAST(d.TotalAmt AS DECIMAL(18,2)) AS DmsAmount,\n    o.TotalAmt AS OmsWmsAmount,\n    s.TotalAmt AS SapAmount,\n    CAST(w.TotalAmt AS DECIMAL(18,2)) AS WrtAmount,\n    CASE\n        WHEN d.OrderCode IS NOT NULL AND s.U_SONo IS NOT NULL AND w.order_number IS NOT NULL\n         AND CAST(d.TotalAmt AS DECIMAL(18,2)) = o.TotalAmt\n         AND o.TotalAmt = s.TotalAmt\n         AND s.TotalAmt = CAST(w.TotalAmt AS DECIMAL(18,2))\n        THEN 'Sync' ELSE 'Not Sync'\n    END AS StatusSync,\n    d.OrderStatus AS SoStatus,\n    o.OrderDate,\n    SYSUTCDATETIME()\nFROM OMS o\nLEFT JOIN DMS_DONE d ON d.OrderCode = o.order_number\nLEFT JOIN SAP s ON s.U_SONo = o.order_number\nLEFT JOIN WRT w ON w.order_number = o.order_number;\n"
_WRT_SQL = f"\nWITH WRT AS (\n    SELECT order_number, MAX(OrderStatus) AS OrderStatus, MAX(Type) AS Type,\n           SUM(TRY_CONVERT(DECIMAL(18,4), TotalAmt)) AS TotalAmt,\n           MAX(postingDate) AS OrderDate\n    FROM dbo.WRT_SO\n    WHERE {_WRT_ORDER_FILTER}\n    GROUP BY order_number\n),\nOMS AS (\n    SELECT order_number, SUM(TRY_CONVERT(DECIMAL(18,2), total_amount_after_vat)) AS TotalAmt\n    FROM dbo.OMS_ORDERS\n    GROUP BY order_number\n),\nSAP_LINES AS (\n    SELECT U_SONo, ItemCode, ARNo,\n           CASE WHEN ARNo IS NOT NULL AND ARNo <> ''\n                THEN MAX(TRY_CONVERT(DECIMAL(18,2), ARGTotal))\n                ELSE SUM(TRY_CONVERT(DECIMAL(18,2), TotalAfVAT))\n           END AS ItemAmt\n    FROM dbo.SAP_SO_All\n    GROUP BY U_SONo, ItemCode, ARNo\n),\nSAP AS (\n    SELECT U_SONo, SUM(ItemAmt) AS TotalAmt\n    FROM SAP_LINES\n    GROUP BY U_SONo\n)\n%%INSERT%%\nSELECT\n    w.order_number AS OrderCode,\n    o.TotalAmt AS OmsWmsAmount,\n    s.TotalAmt AS SapAmount,\n    CAST(w.TotalAmt AS DECIMAL(18,2)) AS WrtAmount,\n    CASE\n        WHEN o.order_number IS NOT NULL AND s.U_SONo IS NOT NULL\n         AND o.TotalAmt = s.TotalAmt AND s.TotalAmt = CAST(w.TotalAmt AS DECIMAL(18,2))\n         AND w.OrderStatus IN {_WRT_SHIPPED_STATUS}\n        THEN 'Sync' ELSE 'Not Sync'\n    END AS StatusSync,\n    w.OrderStatus AS SoStatus,\n    w.Type AS Type,\n    w.OrderDate,\n    SYSUTCDATETIME()\nFROM WRT w\nLEFT JOIN OMS o ON o.order_number = w.order_number\nLEFT JOIN SAP s ON s.U_SONo = w.order_number;\n"
_TABLES: dict[str, tuple[tuple[str, ...], str]] = {'RECON_ECOM': (('OrderCode', 'OmsWmsAmount', 'SapAmount', 'WrtAmount', 'StatusSync', 'SoStatus', 'OrderDate'), _ECOM_SQL), 'RECON_DMS_DUYET': (('OrderCode', 'DmsAmount', 'OmsWmsAmount', 'SapAmount', 'StatusSync', 'SoStatus', 'OrderDate'), _DMS_DUYET_SQL), 'RECON_DMS_XUATKHO': (('OrderCode', 'DmsAmount', 'OmsWmsAmount', 'SapAmount', 'WrtAmount', 'StatusSync', 'SoStatus', 'OrderDate'), _DMS_XUATKHO_SQL), 'RECON_WRT': (('OrderCode', 'OmsWmsAmount', 'SapAmount', 'WrtAmount', 'StatusSync', 'SoStatus', 'Type', 'OrderDate'), _WRT_SQL)}
_BACKUP_TABLES: dict[str, str] = {name: f'{name}_Backup' for name in _TABLES}
STATUS_TRACKING_TABLE = 'STATUS_TRACKING'
RECON_TYPE: dict[str, str] = {'RECON_ECOM': 'ECOM', 'RECON_DMS_DUYET': 'DMS_DUYET', 'RECON_DMS_XUATKHO': 'DMS_XUATKHO', 'RECON_WRT': 'WRT'}
SALEORDERS_TABLE = 'PGI_SaleOrders'
_SALEORDERS_COLUMN_EXPR: dict[str, tuple[str, str, str, str, str]] = {'RECON_ECOM': ('NULL', 'OmsWmsAmount', 'SapAmount', 'WrtAmount', 'SoStatus'), 'RECON_DMS_DUYET': ('DmsAmount', 'OmsWmsAmount', 'SapAmount', 'NULL', 'SoStatus'), 'RECON_DMS_XUATKHO': ('DmsAmount', 'OmsWmsAmount', 'SapAmount', 'WrtAmount', 'SoStatus'), 'RECON_WRT': ('NULL', 'OmsWmsAmount', 'SapAmount', 'WrtAmount', 'SoStatus')}

def _refresh_table(target_conn: Any, table_name: str) -> int:
    columns, select_sql = _TABLES[table_name]
    cursor = target_conn.cursor()
    cursor.execute(f'DELETE FROM {TARGET_SCHEMA}.{table_name}')
    quoted_cols = ', '.join((f'[{c}]' for c in columns)) + ', RefreshedAt'
    insert_clause = f'INSERT INTO {TARGET_SCHEMA}.{table_name} ({quoted_cols})'
    cursor.execute(select_sql.replace('%%INSERT%%', insert_clause))
    cursor.execute(f'SELECT COUNT(*) FROM {TARGET_SCHEMA}.{table_name}')
    return cursor.fetchone()[0]

def _backup_not_synced(target_conn: Any, table_name: str) -> int:
    columns, _ = _TABLES[table_name]
    backup_table = _BACKUP_TABLES[table_name]
    quoted_cols = ', '.join((f'[{c}]' for c in columns)) + ', RefreshedAt, SnapshotAt'
    select_cols = ', '.join((f'[{c}]' for c in columns)) + ', RefreshedAt, SYSUTCDATETIME()'
    cursor = target_conn.cursor()
    cursor.execute(f"\n        INSERT INTO {TARGET_SCHEMA}.{backup_table} ({quoted_cols})\n        SELECT {select_cols}\n        FROM {TARGET_SCHEMA}.{table_name}\n        WHERE StatusSync = 'Not Sync'\n        ")
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
    cursor.execute(f"\n        MERGE {TARGET_SCHEMA}.{STATUS_TRACKING_TABLE} AS target\n        USING (\n            SELECT OrderCode AS BusinessKey, StatusSync\n            FROM {TARGET_SCHEMA}.{table_name}\n        ) AS source\n        ON target.ReconType = '{recon_type}' AND target.BusinessKey = source.BusinessKey\n        WHEN MATCHED THEN\n            UPDATE SET\n                StatusSync = source.StatusSync,\n                UpdatedAt = SYSUTCDATETIME(),\n                SyncAt = CASE\n                    WHEN source.StatusSync = 'Sync' AND target.StatusSync <> 'Sync' THEN SYSUTCDATETIME()\n                    ELSE target.SyncAt\n                END\n        WHEN NOT MATCHED BY TARGET THEN\n            INSERT (ReconType, BusinessKey, StatusSync, CreatedAt, UpdatedAt, SyncAt)\n            VALUES (\n                '{recon_type}', source.BusinessKey, source.StatusSync,\n                SYSUTCDATETIME(), SYSUTCDATETIME(),\n                CASE WHEN source.StatusSync = 'Sync' THEN SYSUTCDATETIME() ELSE NULL END\n            )\n        WHEN NOT MATCHED BY SOURCE AND target.ReconType = '{recon_type}' THEN\n            DELETE;\n        ")

def _log_refresh(target_conn: Any, table_name: str, row_count: int, status: str) -> None:
    cursor = target_conn.cursor()
    cursor.execute(f'\n        INSERT INTO {TARGET_SCHEMA}.{LOG_TABLE} (table_name, row_count, status, refreshed_at)\n        VALUES (%s, %s, %s, SYSUTCDATETIME())\n        ', (table_name, row_count, status))

INVENTORY_TABLE = 'RECON_INVENTORY'
NON_WMS_WAREHOUSES = ('W101', 'W114', 'W999')
LOC_BASED_WAREHOUSES = ('W998',)
_WMS_STATUS_ITEM_EXPR = f"CASE WHEN 'W' + SUBSTRING(_whseid, 3, 10) IN ({', '.join((f"'{w}'" for w in LOC_BASED_WAREHOUSES))}) THEN ISNULL(loc, '') ELSE ISNULL(status, '') END"
_INVENTORY_SQL = f"""
WITH S AS (
    SELECT ItemCode, WhsCode, StatusItem, MAX(ItemName) AS ItemName, MAX(WhsName) AS WhsName,
           SUM(OnHand) AS Qty, MAX(InvntryUom) AS Uom
    FROM dbo.SAP_INVENTORY
    GROUP BY ItemCode, WhsCode, StatusItem
),
W AS (
    SELECT sku AS ItemCode, 'W' + SUBSTRING(_whseid, 3, 10) AS WhsCode, {_WMS_STATUS_ITEM_EXPR} AS StatusItem,
           MAX(description) AS ItemName, SUM(TRY_CONVERT(DECIMAL(21,6), qty)) AS Qty, MAX(uom) AS Uom
    FROM dbo.WMS_INVENTORY
    GROUP BY sku, _whseid, {_WMS_STATUS_ITEM_EXPR}
),
WHS AS (
    SELECT WhsCode, MAX(WhsName) AS WhsName FROM dbo.SAP_INVENTORY GROUP BY WhsCode
)
INSERT INTO dbo.{INVENTORY_TABLE} (StatusSync, ItemCode, ItemName, WhsCode, WhsName, StatusItem, SapQty, WmsQty, DiffQty, InvntryUom)
SELECT
    CASE
        WHEN s.ItemCode IS NOT NULL AND w.ItemCode IS NOT NULL
            THEN CASE WHEN s.Qty = w.Qty THEN N'Khớp' ELSE N'Lệch' END
        WHEN s.WhsCode IN ({', '.join((f"'{w}'" for w in NON_WMS_WAREHOUSES))}) THEN N'Không quản lý trên WMS'
        WHEN w.ItemCode IS NULL THEN N'Chỉ có SAP'
        ELSE N'Chỉ có WMS'
    END,
    COALESCE(s.ItemCode, w.ItemCode),
    COALESCE(s.ItemName, w.ItemName),
    COALESCE(s.WhsCode, w.WhsCode),
    COALESCE(s.WhsName, whs.WhsName),
    COALESCE(s.StatusItem, w.StatusItem),
    s.Qty,
    w.Qty,
    ABS(ISNULL(s.Qty, 0) - ISNULL(w.Qty, 0)),
    COALESCE(s.Uom, w.Uom)
FROM S s
FULL OUTER JOIN W w ON w.ItemCode = s.ItemCode AND w.WhsCode = s.WhsCode AND w.StatusItem = s.StatusItem
LEFT JOIN WHS whs ON whs.WhsCode = COALESCE(s.WhsCode, w.WhsCode);
"""

def refresh_inventory_reconciliation(target_conn: Any, **_ignored: Any) -> int:
    cursor = target_conn.cursor()
    try:
        cursor.execute(f'DELETE FROM {TARGET_SCHEMA}.{INVENTORY_TABLE}')
        cursor.execute(_INVENTORY_SQL)
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
