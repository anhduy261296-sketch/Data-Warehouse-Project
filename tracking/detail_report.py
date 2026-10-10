from __future__ import annotations
import datetime
import time
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
STATUS_FREE_WAREHOUSES = ('W114', 'W998')
INVENTORY_STATUS_VALUES = ('Khớp', 'Lệch', 'Chỉ có SAP', 'Chỉ có WMS', 'Không quản lý trên WMS')
INVENTORY_CONFIG = DetailReportConfig(table='dbo.RECON_INVENTORY', where='1=1', status_values=INVENTORY_STATUS_VALUES, default_hidden_status='Không quản lý trên WMS', default_order_sql="CASE t.StatusSync WHEN N'Lệch' THEN 0 WHEN N'Chỉ có SAP' THEN 1 WHEN N'Chỉ có WMS' THEN 2 WHEN N'Khớp' THEN 3 ELSE 4 END, ABS(t.DiffQty) DESC, t.ItemCode", filter_params=(('whs_code', 't.WhsCode'),), columns=[DetailColumn('t.StatusSync', 'status_sync', title='Status'), DetailColumn('t.ItemCode', 'item_code', searchable=True, title='ItemCode'), DetailColumn('t.ItemName', 'item_name', searchable=True, title='Tên hàng'), DetailColumn('t.WhsCode', 'whs_code', title='Kho'), DetailColumn('t.WhsName', 'whs_name', title='Tên kho'), DetailColumn('t.StatusItem', 'status_item', searchable=True, title='Trạng thái'), DetailColumn('t.SapQty', 'sap_qty', title='SAP tồn'), DetailColumn('t.WmsQty', 'wms_qty', title='WMS tồn'), DetailColumn('t.DiffQty', 'diff_qty', title='Chênh lệch'), DetailColumn('t.InvntryUom', 'uom', title='ĐVT')])

def get_inventory_meta() -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute('SELECT (SELECT MAX(LoadedAt) FROM dbo.SAP_INVENTORY), (SELECT MAX(_scraped_at) FROM dbo.WMS_INVENTORY), (SELECT MAX(RefreshedAt) FROM dbo.RECON_INVENTORY)')
        sap_at, wms_at, recon_at = cursor.fetchone()
        cursor.execute('SELECT DISTINCT WhsCode, WhsName FROM dbo.RECON_INVENTORY ORDER BY WhsCode')
        warehouses = [{'code': code, 'name': name} for code, name in cursor.fetchall()]
    return {'sap_snapshot_at': _json_safe(sap_at), 'wms_snapshot_at': _json_safe(wms_at), 'recon_refreshed_at': _json_safe(recon_at), 'warehouses': warehouses, 'statuses': list(INVENTORY_STATUS_VALUES), 'summary': get_inventory_summary()}

_INVENTORY_DIFF_STATUSES = ('Lệch', 'Chỉ có SAP', 'Chỉ có WMS')

def get_inventory_summary() -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute('SELECT ISNULL(SUM(SapQty), 0), ISNULL(SUM(WmsQty), 0) FROM dbo.RECON_INVENTORY WHERE StatusSync <> %s', [INVENTORY_CONFIG.default_hidden_status])
        sap_total, wms_total = cursor.fetchone()
    diff = abs(sap_total - wms_total)
    ratio = diff / sap_total * 100 if sap_total else Decimal(0)
    return {'sap_total': _json_safe(sap_total), 'wms_total': _json_safe(wms_total), 'diff_total': _json_safe(diff), 'diff_ratio_pct': _json_safe(ratio)}

def get_inventory_diff_list() -> dict[str, Any]:
    placeholders = ', '.join(('%s' for _ in _INVENTORY_DIFF_STATUSES))
    with connection.cursor() as cursor:
        cursor.execute(f'''
            SELECT StatusSync, ItemCode, ItemName, WhsCode, StatusItem, SapQty, WmsQty, ABS(ISNULL(SapQty, 0) - ISNULL(WmsQty, 0)) AS Diff
            FROM dbo.RECON_INVENTORY
            WHERE StatusSync IN ({placeholders})
            ORDER BY Diff DESC, ItemCode, WhsCode, StatusItem
            ''', list(_INVENTORY_DIFF_STATUSES))
        rows = cursor.fetchall()
    groups = {'Lệch': [], 'Chỉ có SAP': [], 'Chỉ có WMS': []}
    for status_sync, item_code, item_name, whs_code, status_item, sap_qty, wms_qty, diff in rows:
        groups[status_sync].append({'item_code': item_code, 'item_name': item_name, 'whs_code': whs_code, 'status_item': status_item, 'sap_qty': _json_safe(sap_qty), 'wms_qty': _json_safe(wms_qty), 'diff_qty': _json_safe(diff)})
    return {'both': groups['Lệch'], 'sap_only': groups['Chỉ có SAP'], 'wms_only': groups['Chỉ có WMS']}

def _status_after_dash(col: str) -> str:
    return f"CASE WHEN {col} IS NULL THEN '' WHEN CHARINDEX('-', {col}) = 0 THEN {col} ELSE RIGHT({col}, CHARINDEX('-', REVERSE({col})) - 1) END"

_DOC_TYPE_CACHE: dict[str, Any] = {'at': 0.0, 'names': {}, 'sales': set()}
_DOC_TYPE_CACHE_SEC = 600
SAP_DOC_DIRECTION = {15: 'Bán ra', 16: 'Hàng hoàn', 20: 'Nhập mua', 21: 'Trả NCC', 59: 'Nhập khác', 60: 'Xuất khác'}

def _sap_doc_types(cursor: Any) -> tuple[dict[str, str], set[str]]:
    now = time.monotonic()
    if not _DOC_TYPE_CACHE['names'] or now - _DOC_TYPE_CACHE['at'] > _DOC_TYPE_CACHE_SEC:
        cursor.execute('SELECT LoaiCT, MAX(TenLoaiCT), MAX(CASE WHEN DocType IN (15, 16) THEN 1 ELSE 0 END) FROM dbo.SAP_INOUT GROUP BY LoaiCT')
        rows = cursor.fetchall()
        _DOC_TYPE_CACHE['names'] = {code: name for code, name, _ in rows}
        _DOC_TYPE_CACHE['sales'] = {code for code, _, is_sales in rows if is_sales}
        _DOC_TYPE_CACHE['at'] = now
    return _DOC_TYPE_CACHE['names'], _DOC_TYPE_CACHE['sales']

def _sap_doc_label(doc_type: int | None, type_name: str | None, in_whs: str | None, out_whs: str | None) -> str:
    if doc_type == 67:
        direction = 'Chuyển trạng thái' if in_whs and in_whs == out_whs else 'Chuyển kho'
    else:
        direction = SAP_DOC_DIRECTION.get(doc_type, 'Khác')
    return f'{direction} · {type_name}' if type_name else direction

def _wms_doc_label(src: str, code: str | None, names: dict[str, str], sales: set[str]) -> str:
    code = code or ''
    name = names.get(code) or names.get('GR' + code) or names.get('GI' + code) or code
    if src == 'I':
        direction = 'Hàng hoàn' if code in sales else 'Nhập'
    else:
        direction = 'Bán ra' if code in sales else 'Xuất'
    return f'{direction} · {name}' if name else direction

INVENTORY_DETAIL_MAX_ROWS = 20000

def _doc_key(doc_no: str | None) -> str:
    doc_no = (doc_no or '').strip()
    return doc_no[2:] if doc_no[:2] in ('I-', 'O-') else doc_no

def _group_docs(rows: list[tuple]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for doc_no, doc_date, doc_type, qty in rows:
        key = _doc_key(doc_no)
        doc = grouped.setdefault(key, {'doc_no': doc_no, 'doc_date': doc_date, 'doc_type': doc_type, 'qty': Decimal(0)})
        doc['qty'] += qty or 0
        if doc_date and (doc['doc_date'] is None or doc_date > doc['doc_date']):
            doc['doc_date'] = doc_date
    return {key: doc for key, doc in grouped.items() if doc['qty'] != 0}

STATUS_CHANGE_LABEL = 'Chuyển trạng thái'
STATUS_CHANGE_MATCH_DAYS = 3

def _wms_status_change_rows(cursor: Any, item_code: str, whs_code: str, wms_whse: str, status_item: str) -> list[tuple]:
    cursor.execute(f"""
        SELECT TOP {INVENTORY_DETAIL_MAX_ROWS} t.status, t.tostatus, t.trantype, t.sourcekey, t.tolpnid, DATEADD(hour, 7, t.adddate),
               CASE WHEN t.tostatus = %s THEN t.qty ELSE -t.qty END,
               (SELECT TOP 1 i.externreceiptkey FROM dbo.WMS_INBOUND i WHERE i._whseid = t._whseid AND i.lpnid = t.tolpnid)
        FROM dbo.WMS_TRANSACTION t
        WHERE t.sku = %s AND t._whseid = %s AND ISNULL(t.tostatus, '') <> '' AND t.status <> t.tostatus AND (t.status = %s OR t.tostatus = %s)
        ORDER BY t.adddate DESC
        """, [status_item, item_code, wms_whse, status_item, status_item])
    rows = []
    for from_status, to_status, trantype, sourcekey, lpnid, doc_date, qty, receipt in cursor.fetchall():
        doc_no = f'{whs_code}_{receipt}' if receipt else (sourcekey or lpnid)
        rows.append((doc_no, doc_date, f'{STATUS_CHANGE_LABEL} · {from_status} → {to_status} ({trantype})', qty))
    return rows

def _pair_status_changes(sap_docs: dict[str, dict], wms_docs: dict[str, dict]) -> list[tuple[str, str]]:
    def is_change(doc: dict) -> bool:
        return (doc.get('doc_type') or '').startswith(STATUS_CHANGE_LABEL)
    sap_left = sorted((k for k, d in sap_docs.items() if k not in wms_docs and is_change(d)), key=lambda k: sap_docs[k]['doc_date'] or datetime.datetime.min)
    wms_left = [k for k, d in wms_docs.items() if k not in sap_docs and is_change(d)]
    pairs = []
    for sap_key in sap_left:
        sap = sap_docs[sap_key]
        if sap['doc_date'] is None:
            continue
        best, best_gap = None, None
        for wms_key in wms_left:
            wms = wms_docs[wms_key]
            if wms['qty'] != sap['qty'] or wms['doc_date'] is None:
                continue
            gap = abs((wms['doc_date'].date() - sap['doc_date'].date()).days)
            if gap <= STATUS_CHANGE_MATCH_DAYS and (best_gap is None or gap < best_gap):
                best, best_gap = wms_key, gap
        if best is not None:
            pairs.append((sap_key, best))
            wms_left.remove(best)
    return pairs

def _sort_by_date(docs: list[dict[str, Any]], key: str='doc_date') -> list[dict[str, Any]]:
    return sorted(docs, key=lambda d: (d[key] is not None, d[key] or datetime.datetime.min, d['doc_no'] or ''), reverse=True)

def get_inventory_detail(item_code: str, whs_code: str, status_item: str) -> dict[str, Any]:
    wms_whse = 'WH' + whs_code[1:] if whs_code.startswith('W') else whs_code
    status_free = whs_code in STATUS_FREE_WAREHOUSES
    if status_free:
        in_match, in_params = 't.IN_WhsCode = %s', [whs_code]
        out_match, out_params = 't.OUT_WhsCode = %s', [whs_code]
        wms_status_sql, wms_status_params = '', []
    else:
        in_match, in_params = f"(t.IN_WhsCode = %s AND {_status_after_dash('t.IN_BinCode')} = %s)", [whs_code, status_item]
        out_match, out_params = f"(t.OUT_WhsCode = %s AND {_status_after_dash('t.OUT_BinCode')} = %s)", [whs_code, status_item]
        wms_status_sql, wms_status_params = "AND ISNULL(t.conditioncode, '') = %s", [status_item]
    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT TOP {INVENTORY_DETAIL_MAX_ROWS} t.SoCT_NhapXuat, t.DocDate_NhapXuat, t.DocType, t.TenLoaiCT, t.IN_WhsCode, t.OUT_WhsCode,
                   CASE WHEN {in_match} THEN t.InStock ELSE 0 END - CASE WHEN {out_match} THEN t.InStock ELSE 0 END
            FROM dbo.SAP_INOUT t
            WHERE t.ItemCode = %s AND ({in_match} OR {out_match})
            ORDER BY t.DocDate_NhapXuat DESC
            """, [*in_params, *out_params, item_code, *in_params, *out_params])
        sap_rows = cursor.fetchall()
        cursor.execute(f"""
            SELECT TOP {INVENTORY_DETAIL_MAX_ROWS} doc_no, doc_date, src, doc_type, qty FROM (
                SELECT t.externreceiptkey AS doc_no, TRY_CONVERT(DATETIME2, ISNULL(t.datereceived, t.adddate)) AS doc_date, 'I' AS src, t.type AS doc_type,
                       TRY_CONVERT(DECIMAL(21,6), t.qtyreceivedpcs) AS qty
                FROM dbo.WMS_INBOUND t
                WHERE t.sku = %s AND t._whseid = %s {wms_status_sql} AND TRY_CONVERT(DECIMAL(21,6), t.qtyreceivedpcs) <> 0
                UNION ALL
                SELECT t.externorderkey, MAX(TRY_CONVERT(DATETIME2, ISNULL(t.actualshipdate, t.adddate))), 'O', MAX(t.type),
                       -MAX(TRY_CONVERT(DECIMAL(21,6), t.shippedqtypcs))
                FROM dbo.WMS_OUTBOUND t
                WHERE t.sku = %s AND t._whseid = %s {wms_status_sql} AND TRY_CONVERT(DECIMAL(21,6), t.shippedqtypcs) <> 0
                GROUP BY t.externorderkey, t.orderkey, t.orderlinenumber
            ) x
            ORDER BY doc_date DESC
            """, [item_code, wms_whse, *wms_status_params, item_code, wms_whse, *wms_status_params])
        wms_rows = cursor.fetchall()
        names, sales = _sap_doc_types(cursor)
        change_rows = [] if status_free else _wms_status_change_rows(cursor, item_code, whs_code, wms_whse, status_item)
    sap_rows = [(doc_no, doc_date, _sap_doc_label(doc_type, type_name, in_whs, out_whs), qty) for doc_no, doc_date, doc_type, type_name, in_whs, out_whs, qty in sap_rows]
    wms_rows = [(doc_no, doc_date, _wms_doc_label(src, code, names, sales), qty) for doc_no, doc_date, src, code, qty in wms_rows] + change_rows
    sap_docs, wms_docs = _group_docs(sap_rows), _group_docs(wms_rows)
    matches = [(key, key) for key in sap_docs.keys() & wms_docs.keys()] + _pair_status_changes(sap_docs, wms_docs)
    both = []
    for sap_key, wms_key in matches:
        sap, wms = sap_docs[sap_key], wms_docs[wms_key]
        both.append({'doc_no': sap_key, 'wms_doc_no': wms['doc_no'] if wms_key != sap_key else None, 'sap_date': sap['doc_date'], 'wms_date': wms['doc_date'], 'doc_date': sap['doc_date'] or wms['doc_date'], 'doc_type': sap['doc_type'] or wms['doc_type'], 'wms_doc_type': wms['doc_type'], 'sap_qty': sap['qty'], 'wms_qty': wms['qty'], 'diff_qty': abs(sap['qty'] - wms['qty'])})
    matched_sap = {k for k, _ in matches}
    matched_wms = {k for _, k in matches}
    sap_only = [doc for key, doc in sap_docs.items() if key not in matched_sap]
    wms_only = [doc for key, doc in wms_docs.items() if key not in matched_wms]
    result = {'both': _sort_by_date(both), 'sap_only': _sort_by_date(sap_only), 'wms_only': _sort_by_date(wms_only), 'truncated': len(sap_rows) >= INVENTORY_DETAIL_MAX_ROWS or len(wms_rows) >= INVENTORY_DETAIL_MAX_ROWS}
    for key in ('both', 'sap_only', 'wms_only'):
        result[key] = [{col: _json_safe(value) for col, value in doc.items()} for doc in result[key]]
    return result
