"""Bao cao > E-commerce: KPI, doanh thu theo ngay / Sale, top san pham, bang chi tiet.

Nguon: view dbo.ECOM_ORDER_LINES (db_migrations/0024) - quy tac doanh thu / trang thai / qua tang KM nam trong view.
Moi API nhan cung bo loc: date_from, date_to (ngay VN yyyy-mm-dd), channel (ma san), shop (shop_id).
"""

from __future__ import annotations
import datetime as dt
from typing import Any
from django.db import connection

from ..constants import ECOM_MAX_RANGE_DAYS, ECOM_TOP_LIMIT
from ..core.cache import SOURCES, cached
from ..core.datatables import DetailColumn, DetailReportConfig
from ..core.sql import num, rows as fetch_rows

ECOM_SOURCES = ('oms_orders', 'oms_sales_channels', 'sap_items')
_FROM = 'FROM dbo.ECOM_ORDER_LINES t'
# don "hop le" (khong huy) - dung cho so don theo ngay / Sale / san
_VALID_ORDER = "CASE WHEN t.order_type = 'Sales' AND t.status_group <> 'cancel' THEN t.order_number END"


def _today_vn() -> dt.date:
    return (dt.datetime.utcnow() + dt.timedelta(hours=7)).date()


def _period(params: Any) -> tuple[dt.date, dt.date]:
    """Khoang ngay VN cua bao cao; thieu / sai -> thang hien tai. Qua dai -> cat con ECOM_MAX_RANGE_DAYS."""
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
    # loc tren cot UTC co index (gio VN 00:00 = 17:00 UTC ngay truoc)
    where = [
        't.created_at_utc >= DATEADD(HOUR, -7, CAST(%s AS DATETIME2))',
        't.created_at_utc < DATEADD(HOUR, -7, DATEADD(DAY, 1, CAST(%s AS DATETIME2)))',
    ]
    args: list[Any] = [d_from.isoformat(), d_to.isoformat()]
    for param, column in (('channel', 't.sales_channel'), ('shop', 't.shop_id')):
        value = (params.get(param) or '').strip()
        if value:
            where.append(f'{column} = %s')
            args.append(value)
    return ' AND '.join(where), args


def _query(sql: str, args: list[Any]) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(sql, args)
        return fetch_rows(cursor)


@cached(*ECOM_SOURCES)
def get_meta(_params: Any = None) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT CONVERT(CHAR(7), t.created_at, 126) AS month, MIN(CAST(t.created_at AS DATE)), MAX(CAST(t.created_at AS DATE))
            {_FROM} GROUP BY CONVERT(CHAR(7), t.created_at, 126) ORDER BY month DESC
            """)
        months = [{'value': m, 'first_day': f.isoformat(), 'last_day': last.isoformat()} for m, f, last in cursor.fetchall()]
        # dropdown San: danh muc kenh ban OMS (online + offline, dang Active) + ma kenh co trong du lieu ma danh muc chua co
        cursor.execute(f"""
            SELECT c.code, c.operation, CASE WHEN c.operation = 'online' AND ISNULL(c.display_name, N'') <> N'' THEN c.display_name ELSE c.code END
            FROM dbo.OMS_SALES_CHANNELS c WHERE c.status = 'Active'
            UNION
            SELECT t.sales_channel, NULL, MAX(t.channel_name) {_FROM}
            WHERE NOT EXISTS (SELECT 1 FROM dbo.OMS_SALES_CHANNELS c WHERE c.code = t.sales_channel AND c.status = 'Active')
            GROUP BY t.sales_channel
            """)
        channels = sorted(
            ({'code': c, 'operation': op, 'name': n} for c, op, n in cursor.fetchall()),
            key=lambda c: ({'online': 0, 'offline': 1}.get(c['operation'], 2), c['name']),
        )
        cursor.execute(
            f'SELECT t.sales_channel, t.shop_id, MAX(t.shop_name) AS name {_FROM} GROUP BY t.sales_channel, t.shop_id ORDER BY t.sales_channel, name'
        )
        shops = [{'channel': c, 'id': i, 'name': n} for c, i, n in cursor.fetchall()]
        cursor.execute(SOURCES['oms_orders'])  # thoi diem nap OMS gan nhat (cung SQL voi phien ban cache)
        updated_at = cursor.fetchone()[0]
        cursor.execute(SOURCES['oms_sales_channels'])
        channels_loaded_at = cursor.fetchone()[0]
    return {
        'months': months,
        'channels': channels,
        'shops': shops,
        'max_range_days': ECOM_MAX_RANGE_DAYS,
        'updated_at': updated_at.isoformat() if updated_at else None,
        'channels_loaded_at': channels_loaded_at.isoformat() if channels_loaded_at else None,
    }


@cached(*ECOM_SOURCES)
def get_kpi(params: Any) -> dict[str, Any]:
    """Phan loai theo DON: huy > tra hang > thanh cong > dang xu ly (don co dong tra hang khong huy = tra hang)."""
    where, args = _filters(params)
    rows = _query(
        f"""
        ;WITH o AS (
            SELECT t.order_number,
                   MAX(CASE WHEN t.order_type = 'Sales' THEN 1 ELSE 0 END) AS has_sale,
                   -- don huy = moi dong ban deu huy (don huy 1 phan van tinh la don hop le, khop so don o bieu do)
                   1 - MAX(CASE WHEN t.order_type = 'Sales' AND t.status_group <> 'cancel' THEN 1 ELSE 0 END) AS is_cancel,
                   MAX(CASE WHEN (t.order_type = 'Return' AND t.status_group <> 'cancel')
                              OR (t.order_type = 'Sales' AND t.status_group = 'return') THEN 1 ELSE 0 END) AS is_return,
                   MAX(CASE WHEN t.order_type = 'Sales' AND t.status_group = 'success' THEN 1 ELSE 0 END) AS is_success,
                   SUM(t.net_amount) AS revenue
            {_FROM} WHERE {where} GROUP BY t.order_number
        )
        SELECT ISNULL(SUM(revenue), 0) AS revenue,
               ISNULL(SUM(has_sale), 0) AS total_orders,
               ISNULL(SUM(CASE WHEN has_sale = 1 AND is_cancel = 1 THEN 1 ELSE 0 END), 0) AS cancel_orders,
               ISNULL(SUM(CASE WHEN has_sale = 1 AND is_cancel = 0 AND is_return = 1 THEN 1 ELSE 0 END), 0) AS return_orders,
               ISNULL(SUM(CASE WHEN has_sale = 1 AND is_cancel = 0 AND is_return = 0 AND is_success = 1 THEN 1 ELSE 0 END), 0) AS success_orders
        FROM o
        """,
        args,
    )
    kpi = rows[0]
    total = kpi['total_orders'] or 0
    valid = total - (kpi['cancel_orders'] or 0)
    kpi['processing_orders'] = total - kpi['cancel_orders'] - kpi['return_orders'] - kpi['success_orders']
    kpi['success_rate'] = kpi['success_orders'] / total if total else None
    kpi['cancel_return_rate'] = (kpi['cancel_orders'] + kpi['return_orders']) / total if total else None
    # gia tri don TB = doanh thu / so don khong huy (doanh thu da loai don huy)
    kpi['avg_order_value'] = kpi['revenue'] / valid if valid else None
    return kpi


@cached(*ECOM_SOURCES)
def get_daily(params: Any) -> dict[str, Any]:
    where, args = _filters(params)
    rows = _query(
        f"""
        SELECT CAST(t.created_at AS DATE) AS day, SUM(t.net_amount) AS revenue, COUNT(DISTINCT {_VALID_ORDER}) AS orders
        {_FROM} WHERE {where} GROUP BY CAST(t.created_at AS DATE)
        """,
        args,
    )
    by_day = {r['day']: r for r in rows}
    d_from, d_to = _period(params)
    data = []
    day = d_from
    while day <= d_to:  # du moi ngay trong ky (ngay khong co don = 0) de truc ngay lien tuc
        r = by_day.get(day, {})
        data.append({'day': day.isoformat(), 'revenue': r.get('revenue') or 0, 'orders': r.get('orders') or 0})
        day += dt.timedelta(days=1)
    return {'data': data}


@cached(*ECOM_SOURCES)
def get_by_sale(params: Any) -> dict[str, Any]:
    where, args = _filters(params)
    rows = _query(
        f"""
        SELECT ISNULL(t.employee_code, '') AS code, ISNULL(MAX(t.employee_name), N'(Chưa gán Sale)') AS name,
               SUM(t.net_amount) AS revenue, COUNT(DISTINCT {_VALID_ORDER}) AS orders
        {_FROM} WHERE {where} GROUP BY t.employee_code ORDER BY revenue DESC
        """,
        args,
    )
    return {'data': rows}


@cached(*ECOM_SOURCES)
def get_top_products(params: Any) -> dict[str, Any]:
    """Top san pham theo doanh thu va theo so luong (khong tinh qua tang KM; hang tra da tru)."""
    where, args = _filters(params)
    rows = _query(
        f"""
        SELECT t.sku, MAX(t.item_name) AS item_name, SUM(t.net_qty) AS qty, SUM(t.net_amount) AS revenue
        {_FROM} WHERE {where} AND t.is_gift = 0 GROUP BY t.sku
        """,
        args,
    )
    total_revenue = sum(r['revenue'] or 0 for r in rows)
    total_qty = sum(r['qty'] or 0 for r in rows)
    for r in rows:
        r['revenue_share'] = (r['revenue'] or 0) / total_revenue if total_revenue else None
        r['qty_share'] = (r['qty'] or 0) / total_qty if total_qty else None
    by_revenue = sorted(rows, key=lambda r: (-(r['revenue'] or 0), r['sku']))[:ECOM_TOP_LIMIT]
    by_qty = sorted(rows, key=lambda r: (-(r['qty'] or 0), -(r['revenue'] or 0), r['sku']))[:ECOM_TOP_LIMIT]
    return {'by_revenue': by_revenue, 'by_qty': by_qty, 'total_revenue': num(total_revenue), 'total_qty': num(total_qty)}


# ---- Bang chi tiet (DataTables server-side dung bo may chung) ------------------------------------------
# Loc ngay qua date_from/date_to giong cac API tren (gio VN); bang chi tiet tu cat khoang > MAX_DATE_RANGE_DAYS.
ECOM_DETAIL_CONFIG = DetailReportConfig(
    table='dbo.ECOM_ORDER_LINES',
    where='1=1',
    row_key='_row_id',
    cache_sources=ECOM_SOURCES,
    date_expr='t.created_at',
    default_order_sql='t.created_at',
    filter_params=(('channel', 't.sales_channel'), ('shop', 't.shop_id'), ('status_group', 't.status_group'), ('sku', 't.sku')),
    columns=[
        DetailColumn('t.created_at', 'created_at', title='Ngày tạo'),
        DetailColumn('t.order_number', 'order_number', searchable=True, title='Mã đơn'),
        DetailColumn('t.channel_name', 'channel_name', title='Sàn'),
        DetailColumn('t.shop_name', 'shop_name', searchable=True, title='Gian hàng'),
        DetailColumn('t.employee_name', 'employee_name', searchable=True, title='Sale'),
        DetailColumn('t.status', 'status', title='Trạng thái OMS'),
        DetailColumn('t.status_group_label', 'status_group_label', title='Nhóm trạng thái'),
        DetailColumn('t.line_type', 'line_type', title='Dòng'),
        DetailColumn('t.item_kind', 'item_kind', title='Loại'),
        DetailColumn('t.sku', 'sku', searchable=True, title='SKU'),
        DetailColumn('t.item_name', 'item_name', searchable=True, title='Tên sản phẩm'),
        DetailColumn('t.quantity', 'quantity', title='SL'),
        DetailColumn('t.amount_before_vat', 'amount_before_vat', title='Trước VAT'),
        DetailColumn('t.amount', 'amount', title='Sau VAT'),
        DetailColumn('t.net_amount', 'net_amount', title='Doanh thu tính BC'),
    ],
)
