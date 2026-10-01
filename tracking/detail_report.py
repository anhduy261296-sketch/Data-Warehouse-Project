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
    if status_sync_filter in ('Sync', 'Not Sync'):
        where_extra += f" AND ISNULL({config.status_sync_expr}, 'Not Sync') = %s"
        query_params.append(status_sync_filter)
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
    default_order_expr = f"CASE WHEN {config.status_sync_expr} = 'Not Sync' THEN 0 WHEN {config.status_sync_expr} IS NULL THEN 1 ELSE 2 END"
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
