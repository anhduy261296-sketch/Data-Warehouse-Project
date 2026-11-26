from __future__ import annotations

import datetime as dt
from typing import Any

from django.db import connection

from ..constants import ECOM_MAX_RANGE_DAYS
from ..core.cache import cached
from ..core.datatables import DetailColumn, DetailReportConfig
from ..core.sql import num, rows as fetch_rows

DMS_SOURCES = ('oms_orders',)
DMS_CODE_FILTER = "LEFT(t.outbound_order_type, 2) = 'L0' AND t.outbound_order_type NOT IN ('L03', 'L04')"
_FROM = 'FROM dbo.OMS_ORDERS t'
_REPORT_DATE = 'DATEADD(HOUR, 7, t._k_created_at)'
_CANCEL_STATUSES = "('Cancelled', 'Cancel', 'InCancel')"
_SUCCESS_STATUSES = "('Delivered', 'Shipped')"
_RETURN_STATUSES = "('PackageReturned', 'Refunded', 'Returned', 'Returning', 'RefundRejected', 'PackageReturn', 'Lostdamaged')"


def _today_vn() -> dt.date:
    return (dt.datetime.utcnow() + dt.timedelta(hours=7)).date()


def _period(params: Any) -> tuple[dt.date, dt.date]:
    try:
        d_from = dt.date.fromisoformat((params.get('date_from') or '').strip())
        d_to = dt.date.fromisoformat((params.get('date_to') or '').strip())
    except ValueError:
        d_to = _today_vn()
        d_from = d_to.replace(day=1)
    if d_to < d_from:
        d_from, d_to = d_to, d_from
    if (d_to - d_from).days > ECOM_MAX_RANGE_DAYS:
        d_from = d_to - dt.timedelta(days=ECOM_MAX_RANGE_DAYS)
    return d_from, d_to


def _filters(params: Any) -> tuple[str, list[Any]]:
    d_from, d_to = _period(params)
    where = [
        DMS_CODE_FILTER,
        f'{_REPORT_DATE} >= CAST(%s AS DATETIME2)',
        f'{_REPORT_DATE} < DATEADD(DAY, 1, CAST(%s AS DATETIME2))',
    ]
    args: list[Any] = [d_from.isoformat(), d_to.isoformat()]
    for param, column in (
        ('document_type', 't.outbound_order_type'),
        ('state_code', 't.status'),
        ('order_type', 't.order_type'),
        ('source_warehouse_code', 't.warehouse_code'),
    ):
        value = (params.get(param) or '').strip()
        if value:
            where.append(f'{column} = %s')
            args.append(value)
    return ' AND '.join(where), args


def _query(sql: str, args: list[Any]) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(sql, args)
        return fetch_rows(cursor)


@cached(*DMS_SOURCES)
def get_meta(_params: Any = None) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT CONVERT(CHAR(7), {_REPORT_DATE}, 126) AS month '
            f'{_FROM} WHERE {DMS_CODE_FILTER} GROUP BY CONVERT(CHAR(7), {_REPORT_DATE}, 126) ORDER BY month DESC'
        )
        months = [{'value': row[0]} for row in cursor.fetchall()]
        cursor.execute(
            f'SELECT DISTINCT t.outbound_order_type {_FROM} WHERE {DMS_CODE_FILTER} '
            'AND t.outbound_order_type IS NOT NULL ORDER BY t.outbound_order_type'
        )
        document_types = [row[0] for row in cursor.fetchall()]
        cursor.execute(
            f'SELECT t.status, MAX(t.status) {_FROM} WHERE {DMS_CODE_FILTER} AND t.status IS NOT NULL '
            'GROUP BY t.status ORDER BY t.status'
        )
        states = [{'code': code, 'name': name or code} for code, name in cursor.fetchall()]
        cursor.execute(
            f'SELECT DISTINCT t.order_type {_FROM} WHERE {DMS_CODE_FILTER} '
            'AND t.order_type IS NOT NULL ORDER BY t.order_type'
        )
        order_types = [row[0] for row in cursor.fetchall()]
        cursor.execute(
            f'SELECT t.warehouse_code, MAX(t.warehouse_code) {_FROM} WHERE {DMS_CODE_FILTER} '
            'AND t.warehouse_code IS NOT NULL GROUP BY t.warehouse_code ORDER BY t.warehouse_code'
        )
        warehouses = [{'code': code, 'name': name or code} for code, name in cursor.fetchall()]
        cursor.execute('SELECT MAX(loaded_at) FROM dbo.OMS_ORDERS_Load_Log WHERE status = %s', ['SUCCESS'])
        updated_at = cursor.fetchone()[0]
    return {
        'months': months,
        'document_types': document_types,
        'states': states,
        'order_types': order_types,
        'warehouses': warehouses,
        'max_range_days': ECOM_MAX_RANGE_DAYS,
        'updated_at': updated_at.isoformat() if updated_at else None,
    }


@cached(*DMS_SOURCES)
def get_kpi(params: Any) -> dict[str, Any]:
    where, args = _filters(params)
    rows = _query(
        f"""
        ;WITH filtered AS (
            SELECT t.order_number, t.order_type, t.status, NULLIF(t.customer_code, '') AS customer_code,
                   NULLIF(t.logistic_sku, '') AS logistic_sku,
                   TRY_CONVERT(DECIMAL(28, 6), t.quantity) AS quantity,
                   TRY_CONVERT(DECIMAL(28, 6), t.total_amount_after_vat) AS line_amount
            {_FROM} WHERE {where}
        ), order_metrics AS (
            SELECT order_number, order_type,
                   MAX(CASE WHEN status IN {_CANCEL_STATUSES} THEN 1 ELSE 0 END) AS is_cancel,
                   MAX(CASE WHEN status IN {_SUCCESS_STATUSES} THEN 1 ELSE 0 END) AS is_success,
                   MAX(CASE WHEN status IN {_RETURN_STATUSES} THEN 1 ELSE 0 END) AS has_return_status,
                   MAX(CASE WHEN status IN ('Created', 'Approved', 'Reserved') THEN 1 ELSE 0 END) AS is_new,
                   COUNT(DISTINCT logistic_sku) AS sku_count,
                   SUM(ISNULL(quantity, 0)) AS quantity_total,
                   SUM(ISNULL(line_amount, 0)) AS amount_total,
                   MAX(customer_code) AS customer_code
            FROM filtered
            GROUP BY order_number, order_type
        )
        SELECT         COUNT(CASE WHEN order_type = 'Sales' THEN 1 END) AS total_orders,
        COUNT(CASE WHEN order_type = 'Sales' AND is_cancel = 0 THEN 1 END) AS valid_orders,
        COUNT(CASE WHEN order_type = 'Sales' AND is_cancel = 0 THEN 1 END) AS sale_orders,
        COUNT(CASE WHEN order_type = 'Sales' AND is_cancel = 0 AND is_new = 1 THEN 1 END) AS new_orders,
               COUNT(CASE WHEN order_type = 'Sales' AND is_cancel = 0 AND is_success = 0
                                AND is_new = 0 AND has_return_status = 0 THEN 1 END) AS processing_orders,
               COUNT(CASE WHEN order_type = 'Sales' AND is_cancel = 0 AND is_success = 1 THEN 1 END) AS success_orders,
               COUNT(CASE WHEN order_type = 'Sales' AND is_cancel = 1 THEN 1 END) AS cancel_orders,
               COUNT(CASE WHEN (order_type = 'Return' AND is_cancel = 0)
                                OR (order_type = 'Sales' AND is_cancel = 0 AND has_return_status = 1) THEN 1 END) AS return_orders,
               COUNT(DISTINCT CASE WHEN order_type = 'Sales' THEN customer_code END) AS customers,
               ISNULL(SUM(CASE WHEN order_type = 'Sales' AND is_cancel = 0 THEN amount_total ELSE 0 END), 0) AS amount_total,
               SUM(CASE WHEN order_type = 'Sales' AND is_cancel = 0 THEN sku_count ELSE 0 END) AS sku_sum,
               SUM(CASE WHEN order_type = 'Sales' AND is_cancel = 0 THEN quantity_total ELSE 0 END) AS quantity_sum,
               COUNT(CASE WHEN order_type = 'Sales' AND is_cancel = 0 THEN 1 END) AS metric_orders,
               COUNT(CASE WHEN order_type = 'Sales' OR (order_type = 'Return' AND is_cancel = 0) THEN 1 END) AS all_documents
        FROM order_metrics
        """,
        args,
    )
    kpi = {key: num(value) for key, value in rows[0].items()}
    valid_orders = kpi.pop('valid_orders')
    all_documents = kpi.pop('all_documents')
    metric_orders = kpi.pop('metric_orders')
    sku_sum = kpi.pop('sku_sum')
    quantity_sum = kpi.pop('quantity_sum')
    kpi['avg_order_value'] = kpi['amount_total'] / valid_orders if valid_orders else 0
    kpi['avg_sku_per_order'] = sku_sum / metric_orders if metric_orders else None
    kpi['avg_qty_per_order'] = quantity_sum / metric_orders if metric_orders else None
    for key in ('new', 'processing', 'success', 'cancel', 'return'):
        denominator = all_documents if key == 'return' else kpi['total_orders']
        kpi[f'{key}_rate'] = kpi[f'{key}_orders'] / denominator if denominator else None
    return kpi


@cached(*DMS_SOURCES)
def get_daily(params: Any) -> dict[str, Any]:
    where, args = _filters(params)
    rows = _query(
        f"""
        SELECT CAST({_REPORT_DATE} AS DATE) AS day,
               ISNULL(SUM(CASE WHEN t.order_type = 'Sales' AND t.status NOT IN {_CANCEL_STATUSES}
                               THEN TRY_CONVERT(DECIMAL(28, 6), t.total_amount_after_vat) ELSE 0 END), 0) AS amount_total,
               COUNT(DISTINCT CASE WHEN t.order_type = 'Sales' THEN t.order_number END) AS orders
        {_FROM} WHERE {where} GROUP BY CAST({_REPORT_DATE} AS DATE)
        """,
        args,
    )
    by_day = {row['day']: row for row in rows}
    d_from, d_to = _period(params)
    data = []
    day = d_from
    while day <= d_to:
        row = by_day.get(day, {})
        data.append({'day': day.isoformat(), 'amount_total': num(row.get('amount_total')), 'orders': row.get('orders', 0)})
        day += dt.timedelta(days=1)
    return {'data': data}


@cached(*DMS_SOURCES)
def get_by_sale(params: Any) -> dict[str, Any]:
    where, args = _filters(params)
    rows = _query(
        f"""
        SELECT ISNULL(NULLIF(t.employee_name, ''), N'(Chưa gán Sale)') AS salesperson,
               COUNT(DISTINCT CASE WHEN t.order_type = 'Sales' THEN t.order_number END) AS orders,
               ISNULL(SUM(CASE WHEN t.order_type = 'Sales' AND t.status NOT IN {_CANCEL_STATUSES}
                               THEN TRY_CONVERT(DECIMAL(28, 6), t.total_amount_after_vat) ELSE 0 END), 0) AS amount_total
        {_FROM} WHERE {where}
        GROUP BY NULLIF(t.employee_name, '') ORDER BY amount_total DESC
        """,
        args,
    )
    return {'data': rows}


@cached(*DMS_SOURCES)
def get_top_customers(params: Any) -> dict[str, Any]:
    where, args = _filters(params)
    rows = _query(
        f"""
        SELECT ISNULL(NULLIF(t.customer_code, ''), N'(Chưa có mã)') AS partner_code,
               ISNULL(MAX(NULLIF(t.customer_name, '')), N'(Chưa có tên khách hàng)') AS partner_name,
               COUNT(DISTINCT CASE WHEN t.order_type = 'Sales' THEN t.order_number END) AS orders,
               ISNULL(SUM(CASE WHEN t.order_type = 'Sales' AND t.status NOT IN {_CANCEL_STATUSES}
                               THEN TRY_CONVERT(DECIMAL(28, 6), t.total_amount_after_vat) ELSE 0 END), 0) AS amount_total
        {_FROM} WHERE {where}
        GROUP BY NULLIF(t.customer_code, '')
        """,
        args,
    )
    for row in rows:
        row['amount_total'] = num(row['amount_total'])
    order_rows = [row for row in rows if row['orders']]
    by_amount = sorted(order_rows, key=lambda row: (-(row['amount_total'] or 0), row['partner_code']))[:10]
    by_orders = sorted(order_rows, key=lambda row: (-row['orders'], -(row['amount_total'] or 0), row['partner_code']))[:10]
    return {'by_amount': by_amount, 'by_orders': by_orders}


DMS_OMS_DETAIL_CONFIG = DetailReportConfig(
    table='dbo.OMS_ORDERS',
    where=DMS_CODE_FILTER,
    row_key='_row_id',
    cache_sources=DMS_SOURCES,
    date_expr=_REPORT_DATE,
    default_order_sql=_REPORT_DATE,
    filter_params=(
        ('document_type', 't.outbound_order_type'),
        ('state_code', 't.status'),
        ('order_type', 't.order_type'),
        ('source_warehouse_code', 't.warehouse_code'),
    ),
    columns=[
        DetailColumn(_REPORT_DATE, 'document_date', title='Ngày đơn hàng'),
        DetailColumn('t.outbound_order_type', 'document_type', searchable=True, title='Mã loại đơn DMS'),
        DetailColumn('t.order_number', 'document_code', searchable=True, title='Mã đơn hàng'),
        DetailColumn('t.order_type', 'order_type', title='Loại đơn'),
        DetailColumn('t.customer_code', 'partner_code', searchable=True, title='Mã khách hàng'),
        DetailColumn('t.customer_name', 'partner_name', searchable=True, title='Khách hàng'),
        DetailColumn('t.warehouse_code', 'source_warehouse_code', title='Mã kho'),
        DetailColumn('t.employee_name', 'salesperson', searchable=True, title='Sale'),
        DetailColumn('t.status', 'state', title='Trạng thái đơn hàng'),
        DetailColumn('TRY_CONVERT(DECIMAL(28, 6), t.total_amount_after_vat)', 'amount_total', title='Giá trị dòng hàng'),
        DetailColumn('t.logistic_sku', 'sku', searchable=True, title='SKU'),
        DetailColumn('TRY_CONVERT(DECIMAL(28, 6), t.quantity)', 'quantity', title='Số lượng'),
        DetailColumn('t.sales_channel', 'sales_channel', title='Kênh bán'),
        DetailColumn('t.item_type_display', 'item_type_display', title='Loại dòng hàng'),
    ],
)
