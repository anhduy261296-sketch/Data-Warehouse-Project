from __future__ import annotations

import datetime as dt
from typing import Any

from django.db import connection

from ..constants import ECOM_MAX_RANGE_DAYS
from ..core.cache import cached
from ..core.datatables import DetailColumn, DetailReportConfig
from ..core.sql import num, rows as fetch_rows

DMS_SOURCES = ('dms_so_all',)
_FROM = 'FROM dbo.DMS_SO_ALL t'
_REPORT_DATE = 't.report_date'


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
        f'{_REPORT_DATE} >= CAST(%s AS DATETIME2)',
        f'{_REPORT_DATE} < DATEADD(DAY, 1, CAST(%s AS DATETIME2))',
    ]
    args: list[Any] = [d_from.isoformat(), d_to.isoformat()]
    for param, column in (
        ('document_type', 't.document_type'),
        ('state_code', 't.state_code'),
        ('order_type', 't.order_type'),
        ('source_warehouse_code', 't.source_warehouse_code'),
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
            f'FROM dbo.DMS_SO_ALL t GROUP BY CONVERT(CHAR(7), {_REPORT_DATE}, 126) ORDER BY month DESC'
        )
        months = [{'value': row[0]} for row in cursor.fetchall()]
        cursor.execute('SELECT DISTINCT document_type FROM dbo.DMS_SO_ALL WHERE document_type IS NOT NULL ORDER BY document_type')
        document_types = [row[0] for row in cursor.fetchall()]
        cursor.execute(
            'SELECT state_code, MAX(state) FROM dbo.DMS_SO_ALL WHERE state_code IS NOT NULL GROUP BY state_code ORDER BY state_code'
        )
        states = [{'code': code, 'name': name or code} for code, name in cursor.fetchall()]
        cursor.execute('SELECT DISTINCT order_type FROM dbo.DMS_SO_ALL WHERE order_type IS NOT NULL ORDER BY order_type')
        order_types = [row[0] for row in cursor.fetchall()]
        cursor.execute(
            'SELECT source_warehouse_code, MAX(source_warehouse) FROM dbo.DMS_SO_ALL '
            'WHERE source_warehouse_code IS NOT NULL GROUP BY source_warehouse_code ORDER BY source_warehouse_code'
        )
        warehouses = [{'code': code, 'name': name or code} for code, name in cursor.fetchall()]
        cursor.execute('SELECT MAX(loaded_at) FROM dbo.DMS_SO_ALL_Load_Log WHERE status = %s', ['SUCCESS'])
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
        SELECT COUNT(DISTINCT CASE WHEN t.model IN ('sale.order', 'pos.order')
                                   THEN CONCAT(t.model, ':', t.document_id) END) AS total_orders,
               COUNT(DISTINCT CASE WHEN t.model = 'sale.order' THEN t.document_id END) AS sale_orders,
               COUNT(DISTINCT CASE WHEN t.model = 'pos.order' THEN t.document_id END) AS pos_orders,
               COUNT(DISTINCT CASE WHEN t.model = 'warehouse.transfer' THEN t.document_id END) AS warehouse_transfers,
               COUNT(DISTINCT CASE WHEN (t.model = 'sale.order' AND t.state_code IN ('draft', 'sent', 'to_approve'))
                                         OR (t.model = 'pos.order' AND t.state_code = 'draft')
                                   THEN CONCAT(t.model, ':', t.document_id) END) AS new_orders,
               COUNT(DISTINCT CASE WHEN t.model = 'sale.order' AND t.state_code = 'sale'
                                   THEN CONCAT(t.model, ':', t.document_id) END) AS processing_orders,
               COUNT(DISTINCT CASE WHEN (t.model = 'sale.order' AND t.state_code = 'done')
                                         OR (t.model = 'pos.order' AND t.state_code IN ('paid', 'done', 'invoiced'))
                                   THEN CONCAT(t.model, ':', t.document_id) END) AS success_orders,
               COUNT(DISTINCT CASE WHEN t.model IN ('sale.order', 'pos.order') AND t.state_code = 'cancel'
                                   THEN CONCAT(t.model, ':', t.document_id) END) AS cancel_orders,
               COUNT(DISTINCT CASE WHEN t.model IN ('sale.order', 'pos.order')
                                         AND t.order_type IN ('L10', 'L14') AND t.state_code <> 'cancel'
                                   THEN CONCAT(t.model, ':', t.document_id) END) AS return_orders,
               COUNT(DISTINCT NULLIF(t.partner_code, '')) AS customers,
               ISNULL(SUM(t.amount_total), 0) AS amount_total,
               ISNULL(SUM(ISNULL(t.oms_count, 0)), 0) AS oms_syncs
        {_FROM} WHERE {where}
        """,
        args,
    )
    kpi = {key: num(value) for key, value in rows[0].items()}
    kpi['avg_order_value'] = kpi['amount_total'] / kpi['total_orders'] if kpi['total_orders'] else 0
    for key in ('new', 'processing', 'success', 'cancel', 'return'):
        kpi[f'{key}_rate'] = kpi[f'{key}_orders'] / kpi['total_orders'] if kpi['total_orders'] else None
    return kpi


@cached(*DMS_SOURCES)
def get_daily(params: Any) -> dict[str, Any]:
    where, args = _filters(params)
    rows = _query(
        f"""
        SELECT CAST({_REPORT_DATE} AS DATE) AS day,
               ISNULL(SUM(CASE WHEN ISNULL(t.state_code, '') <> 'cancel' THEN t.amount_total ELSE 0 END), 0) AS amount_total,
               COUNT(DISTINCT CASE WHEN t.model IN ('sale.order', 'pos.order')
                                   THEN CONCAT(t.model, ':', t.document_id) END) AS orders
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
        SELECT ISNULL(NULLIF(t.salesperson, ''), N'(Chưa gán Sale)') AS salesperson,
               COUNT(DISTINCT CASE WHEN t.model IN ('sale.order', 'pos.order')
                                   THEN CONCAT(t.model, ':', t.document_id) END) AS orders,
               ISNULL(SUM(CASE WHEN ISNULL(t.state_code, '') <> 'cancel' THEN t.amount_total ELSE 0 END), 0) AS amount_total
        {_FROM} WHERE {where}
        GROUP BY NULLIF(t.salesperson, '') ORDER BY amount_total DESC
        """,
        args,
    )
    return {'data': rows}


@cached(*DMS_SOURCES)
def get_top_customers(params: Any) -> dict[str, Any]:
    where, args = _filters(params)
    rows = _query(
        f"""
        SELECT ISNULL(NULLIF(t.partner_code, ''), N'(Chưa có mã)') AS partner_code,
               ISNULL(MAX(NULLIF(t.partner_name, '')), N'(Chưa có tên khách hàng)') AS partner_name,
               COUNT(DISTINCT CASE WHEN t.model IN ('sale.order', 'pos.order')
                                   THEN CONCAT(t.model, ':', t.document_id) END) AS orders,
               ISNULL(SUM(CASE WHEN ISNULL(t.state_code, '') <> 'cancel' THEN t.amount_total ELSE 0 END), 0) AS amount_total
        {_FROM} WHERE {where}
        GROUP BY NULLIF(t.partner_code, '')
        """,
        args,
    )
    for row in rows:
        row['amount_total'] = num(row['amount_total'])
    order_rows = [row for row in rows if row['orders']]
    by_amount = sorted(order_rows, key=lambda row: (-(row['amount_total'] or 0), row['partner_code']))[:10]
    by_orders = sorted(order_rows, key=lambda row: (-row['orders'], -(row['amount_total'] or 0), row['partner_code']))[:10]
    return {'by_amount': by_amount, 'by_orders': by_orders}


DMS_ALL_DETAIL_CONFIG = DetailReportConfig(
    table='dbo.DMS_SO_ALL',
    where='1=1',
    row_key='_row_id',
    cache_sources=DMS_SOURCES,
    date_expr='t.report_date',
    default_order_sql='t.report_date',
    filter_params=(
        ('document_type', 't.document_type'),
        ('state_code', 't.state_code'),
        ('order_type', 't.order_type'),
        ('source_warehouse_code', 't.source_warehouse_code'),
    ),
    columns=[
        DetailColumn('t.report_date', 'document_date', title='Ngày đơn hàng'),
        DetailColumn('t.document_type', 'document_type', searchable=True, title='Loại đơn hàng'),
        DetailColumn('t.document_code', 'document_code', searchable=True, title='Mã đơn hàng'),
        DetailColumn('t.order_type', 'order_type', title='Loại đơn'),
        DetailColumn('t.partner_code', 'partner_code', searchable=True, title='Mã khách hàng'),
        DetailColumn('t.partner_name', 'partner_name', searchable=True, title='Khách hàng'),
        DetailColumn('t.source_warehouse_code', 'source_warehouse_code', title='Mã kho'),
        DetailColumn('t.source_warehouse', 'source_warehouse', title='Kho'),
        DetailColumn('t.destination_warehouse_code', 'destination_warehouse_code', title='Mã kho nhận'),
        DetailColumn('t.destination_warehouse', 'destination_warehouse', title='Kho nhận'),
        DetailColumn('t.salesperson', 'salesperson', searchable=True, title='Sale'),
        DetailColumn('t.state', 'state', title='Trạng thái đơn hàng'),
        DetailColumn('t.amount_total', 'amount_total', title='Giá trị đơn hàng'),
        DetailColumn('t.currency', 'currency', title='Loại tiền'),
        DetailColumn('t.oms_count', 'oms_count', title='Lượt sync OMS'),
        DetailColumn('t.oms_codes', 'oms_codes', searchable=True, title='Mã đơn OMS'),
        DetailColumn('t.oms_states', 'oms_states', title='Status sync OMS'),
        DetailColumn('t.created_at', 'created_at', title='Ngày tạo'),
    ],
)
