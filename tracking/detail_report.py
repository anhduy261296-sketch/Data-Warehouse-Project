from __future__ import annotations
import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from django.db import connection
STATUS_TRACKING_TABLE = 'STATUS_TRACKING'
_MAX_PAGE_LENGTH = 200

@dataclass(frozen=True)
class DetailColumn:
    sql_expr: str
    data_key: str
    searchable: bool = False
    orderable: bool = True
    title: str = ''

@dataclass(frozen=True)
class DetailReportConfig:
    table: str
    where: str
    columns: list[DetailColumn] = field(default_factory=list)
    join_sql: str = ''
    status_sync_expr: str = 't.StatusSync'
    so_status_expr: str = 't.SoStatus'
    date_expr: str = ''
    status_values: tuple[str, ...] = ('Sync', 'Not Sync')
    default_hidden_status: str = ''
    default_order_sql: str = ''
    filter_params: tuple[tuple[str, str], ...] = ()

def get_distinct_so_status(config: DetailReportConfig) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(f'\n            SELECT DISTINCT {config.so_status_expr}\n            FROM {config.table} t\n            {config.join_sql}\n            WHERE {config.where} AND {config.so_status_expr} IS NOT NULL\n            ORDER BY {config.so_status_expr}\n            ')
        return [row[0] for row in cursor.fetchall()]

def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    return value
MAX_DATE_RANGE_DAYS = 30

def _build_where_extra(config: DetailReportConfig, params: dict[str, Any]) -> tuple[str, list[Any]]:
    search_value = (params.get('search[value]') or '').strip()
    status_sync_filter = (params.get('status_sync') or '').strip()
    so_status_filter = (params.get('so_status') or '').strip()
    date_from = (params.get('date_from') or '').strip()
    date_to = (params.get('date_to') or '').strip()
    if config.date_expr and date_from and date_to:
        try:
            d_from = datetime.date.fromisoformat(date_from)
            d_to = datetime.date.fromisoformat(date_to)
            if (d_to - d_from).days > MAX_DATE_RANGE_DAYS:
                date_from = (d_to - datetime.timedelta(days=MAX_DATE_RANGE_DAYS)).isoformat()
        except ValueError:
            pass
    where_extra = ''
    query_params: list[Any] = []
    if status_sync_filter in config.status_values:
        where_extra += f" AND ISNULL({config.status_sync_expr}, 'Not Sync') = %s"
        query_params.append(status_sync_filter)
    elif config.default_hidden_status:
        where_extra += f' AND {config.status_sync_expr} <> %s'
        query_params.append(config.default_hidden_status)
    for param_name, sql_expr in config.filter_params:
        value = (params.get(param_name) or '').strip()
        if value:
            where_extra += f' AND {sql_expr} = %s'
            query_params.append(value)
    if so_status_filter:
        where_extra += f' AND {config.so_status_expr} = %s'
        query_params.append(so_status_filter)
    if config.date_expr and date_from:
        where_extra += f' AND {config.date_expr} >= %s'
        query_params.append(date_from)
    if config.date_expr and date_to:
        where_extra += f' AND {config.date_expr} < DATEADD(day, 1, %s)'
        query_params.append(date_to)
    searchable_cols = [c for c in config.columns if c.searchable]
    if search_value and searchable_cols:
        like_clauses = ' OR '.join((f'{c.sql_expr} LIKE %s' for c in searchable_cols))
        where_extra += f' AND ({like_clauses})'
        query_params.extend([f'%{search_value}%'] * len(searchable_cols))
    return (where_extra, query_params)

def run_detail_report(config: DetailReportConfig, params: dict[str, Any]) -> dict[str, Any]:
    draw = int(params.get('draw') or 1)
    start = max(int(params.get('start') or 0), 0)
    length = int(params.get('length') or 10)
    if length <= 0:
        length = _MAX_PAGE_LENGTH
    length = min(length, _MAX_PAGE_LENGTH)
    default_order_expr = config.default_order_sql or f"CASE WHEN {config.status_sync_expr} = 'Not Sync' THEN 0 WHEN {config.status_sync_expr} IS NULL THEN 1 ELSE 2 END"
    order_expr = default_order_expr
    order_dir = 'ASC'
    order_col_idx = params.get('order[0][column]')
    if order_col_idx is not None:
        try:
            col = config.columns[int(order_col_idx)]
        except (ValueError, IndexError):
            col = None
        if col is not None and col.orderable:
            order_expr = col.sql_expr
            order_dir = 'DESC' if (params.get('order[0][dir]') or '').lower() == 'desc' else 'ASC'
    select_list = ', '.join((f'{c.sql_expr} AS [{c.data_key}]' for c in config.columns))
    base_from = f'\n        FROM {config.table} t\n        {config.join_sql}\n        WHERE {config.where}\n    '
    where_extra, query_params = _build_where_extra(config, params)
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) {base_from}')
        records_total = cursor.fetchone()[0]
        cursor.execute(f'SELECT COUNT(*) {base_from} {where_extra}', query_params)
        records_filtered = cursor.fetchone()[0]
        cursor.execute(f'\n            SELECT {select_list}\n            {base_from}\n            {where_extra}\n            ORDER BY {order_expr} {order_dir}\n            OFFSET %s ROWS FETCH NEXT %s ROWS ONLY\n            ', [*query_params, start, length])
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    for row in rows:
        for key, value in row.items():
            row[key] = _json_safe(value)
    return {'draw': draw, 'recordsTotal': records_total, 'recordsFiltered': records_filtered, 'data': rows}
_ECOM_ORDER_FILTER = "t.outbound_order_type IN ('L03', 'L04') AND st.StatusSync = 'Sync'"
_DMS_XUATKHO_ORDER_FILTER = "t.outbound_order_type IN ('L01', 'L05', 'L07', 'L08', 'L12', 'L14', 'L18', 'L25') AND st.StatusSync = 'Sync'"
_WRT_ORDER_FILTER = "t.IsCreateBy = 'SYSTEM' AND st.StatusSync = 'Sync'"
_DMS_DUYET_ORDER_FILTER = "t.OrderStatus = 'sale' AND st.StatusSync = 'Sync'"
_OMS_ORDERS_COLUMNS = [DetailColumn('st.StatusSync', 'status_sync', orderable=False), DetailColumn('t.order_number', 'order_code', searchable=True), DetailColumn('t.logistic_sku', 'sku', searchable=True), DetailColumn('TRY_CONVERT(DECIMAL(18,2), t.quantity)', 'quantity'), DetailColumn('TRY_CONVERT(DECIMAL(18,2), t.total_amount_after_vat)', 'amount'), DetailColumn('t.customer_name', 'customer_name', searchable=True), DetailColumn('t.warehouse_code', 'warehouse_code'), DetailColumn('t.sales_channel', 'sales_channel'), DetailColumn('t.status', 'oms_status'), DetailColumn('t.created_date', 'created_date'), DetailColumn('t.shop_name', 'shop_name'), DetailColumn('t.employee_name', 'employee_name'), DetailColumn('t.phone', 'phone', searchable=True), DetailColumn('t.full_address', 'full_address'), DetailColumn('t.payment_method', 'payment_method'), DetailColumn('t.order_type', 'order_type'), DetailColumn('t.outbound_order_type', 'outbound_order_type'), DetailColumn('t.receiving_status', 'receiving_status'), DetailColumn('t.shipped_date', 'shipped_date'), DetailColumn('t.actual_delivery_date', 'actual_delivery_date'), DetailColumn('t.barcode', 'barcode', searchable=True)]
EMPLOYEE_REPORT_CONFIG_DMS = DetailReportConfig(table='dbo.DMS_SO', where='1=1', status_sync_expr='t.OrderCode', date_expr='t.DocDate', columns=[DetailColumn('t.OrderCode', 'order_code', searchable=True, title='Mã đơn hàng'), DetailColumn('t.SaleEmployeeCode', 'employee_code', searchable=True, title='Mã nhân viên'), DetailColumn('t.CustomerCode', 'customer_code', searchable=True, title='Khách hàng'), DetailColumn('t.ItemCode', 'sku', searchable=True, title='SKU'), DetailColumn('t.Quantity', 'quantity', title='Số lượng'), DetailColumn('t.TotalAmtInclVAT', 'amount', title='Thành tiền'), DetailColumn('t.WarehouseCode', 'warehouse_code', title='Kho'), DetailColumn('t.SalesChannelCode', 'sales_channel', title='Kênh bán'), DetailColumn('t.DocDate', 'order_date', title='Ngày đơn hàng')])
EMPLOYEE_REPORT_CONFIG_OMS = DetailReportConfig(table='dbo.OMS_ORDERS', where='1=1', status_sync_expr='t.order_number', date_expr='TRY_CONVERT(DATETIME2, t.created_date)', columns=[DetailColumn('t.order_number', 'order_code', searchable=True, title='Mã đơn hàng'), DetailColumn('t.employee_code', 'employee_code', searchable=True, title='Mã nhân viên'), DetailColumn('t.employee_name', 'employee_name', searchable=True, title='Tên nhân viên'), DetailColumn('t.customer_code', 'customer_code', searchable=True, title='Khách hàng'), DetailColumn('t.logistic_sku', 'sku', searchable=True, title='SKU'), DetailColumn('TRY_CONVERT(DECIMAL(18,2), t.quantity)', 'quantity', title='Số lượng'), DetailColumn('TRY_CONVERT(DECIMAL(18,2), t.total_amount_after_vat)', 'amount', title='Thành tiền'), DetailColumn('t.warehouse_code', 'warehouse_code', title='Kho'), DetailColumn('t.sales_channel', 'sales_channel', title='Kênh bán'), DetailColumn('TRY_CONVERT(DATETIME2, t.created_date)', 'order_date', title='Ngày đơn hàng')])

def export_detail_report_rows(config: DetailReportConfig, params: dict[str, Any], max_rows: int=50000) -> list[dict]:
    select_list = ', '.join((f'{c.sql_expr} AS [{c.data_key}]' for c in config.columns))
    base_from = f'\n        FROM {config.table} t\n        {config.join_sql}\n        WHERE {config.where}\n    '
    where_extra, query_params = _build_where_extra(config, params)
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT TOP {max_rows} {select_list} {base_from} {where_extra}', query_params)
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    for row in rows:
        for key, value in row.items():
            row[key] = _json_safe(value)
    return rows

def _status_tracking_join(table: str, key_col: str, recon_type: str) -> str:
    return f"LEFT JOIN {STATUS_TRACKING_TABLE} st ON st.BusinessKey = t.{key_col} AND st.ReconType = '{recon_type}'"
DETAIL_CONFIGS: dict[str, DetailReportConfig] = {'ecom': DetailReportConfig(table='dbo.OMS_ORDERS', where=_ECOM_ORDER_FILTER, columns=_OMS_ORDERS_COLUMNS, join_sql=_status_tracking_join('dbo.OMS_ORDERS', 'order_number', 'ECOM'), status_sync_expr='st.StatusSync', date_expr='TRY_CONVERT(DATETIME2, t.created_date)'), 'dms-xuatkho': DetailReportConfig(table='dbo.OMS_ORDERS', where=_DMS_XUATKHO_ORDER_FILTER, columns=_OMS_ORDERS_COLUMNS, join_sql=_status_tracking_join('dbo.OMS_ORDERS', 'order_number', 'DMS_XUATKHO'), status_sync_expr='st.StatusSync', date_expr='TRY_CONVERT(DATETIME2, t.created_date)'), 'dms-duyet': DetailReportConfig(table='dbo.DMS_SO', where=_DMS_DUYET_ORDER_FILTER, join_sql=_status_tracking_join('dbo.DMS_SO', 'OrderCode', 'DMS_DUYET'), status_sync_expr='st.StatusSync', date_expr='t.DocDate', columns=[DetailColumn('st.StatusSync', 'status_sync', orderable=False), DetailColumn('t.OrderCode', 'order_code', searchable=True), DetailColumn('t.ItemCode', 'item_code', searchable=True), DetailColumn('t.Sku', 'sku'), DetailColumn('t.Quantity', 'quantity'), DetailColumn('t.UnitPrice', 'unit_price'), DetailColumn('t.TotalAmtInclVAT', 'amount'), DetailColumn('t.CustomerCode', 'customer_code', searchable=True), DetailColumn('t.WarehouseCode', 'warehouse_code'), DetailColumn('t.OrderStatus', 'order_status'), DetailColumn('t.OMSStatus', 'oms_status'), DetailColumn('t.DocDate', 'doc_date'), DetailColumn('t.SaleEmployeeCode', 'sale_employee_code'), DetailColumn('t.SalesChannelCode', 'sales_channel_code'), DetailColumn('t.CreateDate', 'create_date'), DetailColumn('t.SynDate', 'syn_date'), DetailColumn('t.TaxCode', 'tax_code'), DetailColumn('t.UnitCode', 'unit_code'), DetailColumn('t.Type', 'type'), DetailColumn('t.KeyOrder', 'key_order'), DetailColumn('t.Source', 'source')]), 'wrt': DetailReportConfig(table='dbo.WRT_SO', where=_WRT_ORDER_FILTER, join_sql=_status_tracking_join('dbo.WRT_SO', 'order_number', 'WRT'), status_sync_expr='st.StatusSync', date_expr='t.postingDate', columns=[DetailColumn('st.StatusSync', 'status_sync', orderable=False), DetailColumn('t.order_number', 'order_code', searchable=True), DetailColumn('t.logistic_sku', 'sku', searchable=True), DetailColumn('t.quantity', 'quantity'), DetailColumn('t.TotalAmt', 'amount'), DetailColumn('t.customer_code', 'customer_code', searchable=True), DetailColumn('t.warehouse_code', 'warehouse_code'), DetailColumn('t.sales_channel', 'sales_channel'), DetailColumn('t.OrderStatus', 'order_status'), DetailColumn('t.postingDate', 'posting_date'), DetailColumn('t.Source', 'source'), DetailColumn('t.external_order_key', 'external_order_key'), DetailColumn('t.note', 'note'), DetailColumn('t.currency', 'currency'), DetailColumn('t.VATamount', 'vat_amount'), DetailColumn('t.VATpercent', 'vat_percent'), DetailColumn('t.statusCode', 'status_code'), DetailColumn('t.statusCode2', 'status_code2'), DetailColumn('t.attributes_seller', 'attributes_seller'), DetailColumn('t.LastDt', 'last_dt')])}
RECON_CONFIGS: dict[str, DetailReportConfig] = {'ecom': DetailReportConfig(table='dbo.RECON_ECOM', where='1=1', date_expr='t.OrderDate', columns=[DetailColumn('t.StatusSync', 'status_sync', orderable=False, title='Status Sync'), DetailColumn('t.OrderCode', 'order_code', searchable=True, title='Mã đơn hàng'), DetailColumn('t.OmsWmsAmount', 'oms_wms_amount', title='OMS/WMS'), DetailColumn('t.SapAmount', 'sap_amount', title='SAP'), DetailColumn('t.WrtAmount', 'wrt_amount', title='WRT'), DetailColumn('t.SoStatus', 'so_status', title='SO Status'), DetailColumn('t.OrderDate', 'order_date', title='Ngày đơn hàng'), DetailColumn('t.RefreshedAt', 'refreshed_at', title='Cập nhật lúc')]), 'dms-duyet': DetailReportConfig(table='dbo.RECON_DMS_DUYET', where='1=1', date_expr='t.OrderDate', columns=[DetailColumn('t.StatusSync', 'status_sync', orderable=False, title='Status Sync'), DetailColumn('t.OrderCode', 'order_code', searchable=True, title='Mã đơn hàng'), DetailColumn('t.DmsAmount', 'dms_amount', title='DMS'), DetailColumn('t.OmsWmsAmount', 'oms_wms_amount', title='OMS/WMS'), DetailColumn('t.SapAmount', 'sap_amount', title='SAP'), DetailColumn('t.SoStatus', 'so_status', title='SO Status'), DetailColumn('t.OrderDate', 'order_date', title='Ngày đơn hàng'), DetailColumn('t.RefreshedAt', 'refreshed_at', title='Cập nhật lúc')]), 'dms-xuatkho': DetailReportConfig(table='dbo.RECON_DMS_XUATKHO', where='1=1', date_expr='t.OrderDate', columns=[DetailColumn('t.StatusSync', 'status_sync', orderable=False, title='Status Sync'), DetailColumn('t.OrderCode', 'order_code', searchable=True, title='Mã đơn hàng'), DetailColumn('t.DmsAmount', 'dms_amount', title='DMS'), DetailColumn('t.OmsWmsAmount', 'oms_wms_amount', title='OMS/WMS'), DetailColumn('t.SapAmount', 'sap_amount', title='SAP'), DetailColumn('t.WrtAmount', 'wrt_amount', title='WRT'), DetailColumn('t.SoStatus', 'so_status', title='SO Status'), DetailColumn('t.OrderDate', 'order_date', title='Ngày đơn hàng'), DetailColumn('t.RefreshedAt', 'refreshed_at', title='Cập nhật lúc')]), 'wrt': DetailReportConfig(table='dbo.RECON_WRT', where='1=1', date_expr='t.OrderDate', columns=[DetailColumn('t.StatusSync', 'status_sync', orderable=False, title='Status Sync'), DetailColumn('t.OrderCode', 'order_code', searchable=True, title='Mã đơn hàng'), DetailColumn('t.OmsWmsAmount', 'oms_wms_amount', title='OMS/WMS'), DetailColumn('t.SapAmount', 'sap_amount', title='SAP'), DetailColumn('t.WrtAmount', 'wrt_amount', title='WRT'), DetailColumn('t.SoStatus', 'so_status', title='SO Status'), DetailColumn('t.Type', 'type', title='Loại'), DetailColumn('t.OrderDate', 'order_date', title='Ngày đơn hàng'), DetailColumn('t.RefreshedAt', 'refreshed_at', title='Cập nhật lúc')])}
LOC_BASED_WAREHOUSES = ('W998',)
INVENTORY_STATUS_VALUES = ('Khớp', 'Lệch', 'Chỉ có SAP', 'Chỉ có WMS', 'Không quản lý trên WMS')
INVENTORY_CONFIG = DetailReportConfig(table='dbo.RECON_INVENTORY', where='1=1', status_values=INVENTORY_STATUS_VALUES, default_hidden_status='Không quản lý trên WMS', default_order_sql="CASE t.StatusSync WHEN N'Lệch' THEN 0 WHEN N'Chỉ có SAP' THEN 1 WHEN N'Chỉ có WMS' THEN 2 WHEN N'Khớp' THEN 3 ELSE 4 END, ABS(t.DiffQty) DESC, t.ItemCode", filter_params=(('whs_code', 't.WhsCode'),), columns=[DetailColumn('t.StatusSync', 'status_sync', title='Status'), DetailColumn('t.ItemCode', 'item_code', searchable=True, title='ItemCode'), DetailColumn('t.ItemName', 'item_name', searchable=True, title='Tên hàng'), DetailColumn('t.WhsCode', 'whs_code', title='Kho'), DetailColumn('t.WhsName', 'whs_name', title='Tên kho'), DetailColumn('t.StatusItem', 'status_item', searchable=True, title='Status Item'), DetailColumn('t.SapQty', 'sap_qty', title='SAP tồn'), DetailColumn('t.WmsQty', 'wms_qty', title='WMS tồn'), DetailColumn('t.DiffQty', 'diff_qty', title='Chênh lệch'), DetailColumn('t.InvntryUom', 'uom', title='ĐVT')])

def get_inventory_meta() -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute('SELECT (SELECT MAX(LoadedAt) FROM dbo.SAP_INVENTORY), (SELECT MAX(_scraped_at) FROM dbo.WMS_INVENTORY), (SELECT MAX(RefreshedAt) FROM dbo.RECON_INVENTORY)')
        sap_at, wms_at, recon_at = cursor.fetchone()
        cursor.execute('SELECT DISTINCT WhsCode, WhsName FROM dbo.RECON_INVENTORY ORDER BY WhsCode')
        warehouses = [{'code': code, 'name': name} for code, name in cursor.fetchall()]
    return {'sap_snapshot_at': _json_safe(sap_at), 'wms_snapshot_at': _json_safe(wms_at), 'recon_refreshed_at': _json_safe(recon_at), 'warehouses': warehouses, 'statuses': list(INVENTORY_STATUS_VALUES)}

def _status_after_dash(col: str) -> str:
    return f"CASE WHEN {col} IS NULL THEN '' WHEN CHARINDEX('-', {col}) = 0 THEN {col} ELSE RIGHT({col}, CHARINDEX('-', REVERSE({col})) - 1) END"

def get_inventory_detail(item_code: str, whs_code: str, status_item: str, max_rows: int=200) -> dict[str, Any]:
    wms_whse = 'WH' + whs_code[1:] if whs_code.startswith('W') else whs_code
    loc_based = whs_code in LOC_BASED_WAREHOUSES
    inbound_status_col = 't.toloc' if loc_based else 't.conditioncode'
    outbound_status_col = 't.fromloc' if loc_based else 't.conditioncode'
    in_status = _status_after_dash('t.IN_BinCode')
    out_status = _status_after_dash('t.OUT_BinCode')
    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT TOP {max_rows} t.SoCT_NhapXuat AS doc_no, t.DocDate_NhapXuat AS doc_date, t.TenLoaiCT AS doc_type,
                   CASE WHEN t.IN_WhsCode = %s AND {in_status} = %s THEN t.InStock ELSE -t.InStock END AS qty
            FROM dbo.SAP_INOUT t
            WHERE t.ItemCode = %s
              AND ((t.IN_WhsCode = %s AND {in_status} = %s) OR (t.OUT_WhsCode = %s AND {out_status} = %s))
            ORDER BY t.DocDate_NhapXuat DESC, t.SoCT_NhapXuat DESC
            """, [whs_code, status_item, item_code, whs_code, status_item, whs_code, status_item])
        sap_cols = [d[0] for d in cursor.description]
        sap_rows = [dict(zip(sap_cols, row)) for row in cursor.fetchall()]
        cursor.execute(f"""
            SELECT TOP {max_rows} doc_no, doc_date, doc_type, qty FROM (
                SELECT t.externreceiptkey AS doc_no, TRY_CONVERT(DATETIME2, ISNULL(t.datereceived, t.adddate)) AS doc_date, t.type AS doc_type,
                       TRY_CONVERT(DECIMAL(21,6), t.qtyreceivedpcs) AS qty
                FROM dbo.WMS_INBOUND t
                WHERE t.sku = %s AND t._whseid = %s AND ISNULL({inbound_status_col}, '') = %s AND TRY_CONVERT(DECIMAL(21,6), t.qtyreceivedpcs) <> 0
                UNION ALL
                SELECT t.externorderkey, MAX(TRY_CONVERT(DATETIME2, ISNULL(t.actualshipdate, t.adddate))), MAX(t.type),
                       -MAX(TRY_CONVERT(DECIMAL(21,6), t.shippedqtypcs))
                FROM dbo.WMS_OUTBOUND t
                WHERE t.sku = %s AND t._whseid = %s AND ISNULL({outbound_status_col}, '') = %s AND TRY_CONVERT(DECIMAL(21,6), t.shippedqtypcs) <> 0
                GROUP BY t.externorderkey, t.orderkey, t.orderlinenumber
            ) x
            ORDER BY doc_date DESC, doc_no DESC
            """, [item_code, wms_whse, status_item, item_code, wms_whse, status_item])
        wms_cols = [d[0] for d in cursor.description]
        wms_rows = [dict(zip(wms_cols, row)) for row in cursor.fetchall()]
        cursor.execute('SELECT LoaiCT, MAX(TenLoaiCT) FROM dbo.SAP_INOUT GROUP BY LoaiCT')
        type_names = dict(cursor.fetchall())
    for row in wms_rows:
        code = row.get('doc_type') or ''
        row['doc_type'] = type_names.get(code) or type_names.get('GR' + code) or type_names.get('GI' + code) or code
    for row in [*sap_rows, *wms_rows]:
        for key, value in row.items():
            row[key] = _json_safe(value)
    return {'sap': sap_rows, 'wms': wms_rows}
