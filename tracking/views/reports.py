from __future__ import annotations

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from ..constants import OMS_ORDERS_DAG_ID, OMS_SALES_CHANNELS_DAG_ID
from ..core import airflow
from ..core.cache import invalidate_source
from ..core.excel import ExcelColumn, ExcelSheet, excel_response
from ..reports import ecom, stock


def _json(fn):
    def view(request):
        return JsonResponse(fn(request.GET))

    view.__name__ = fn.__name__
    return view


inventory_meta = _json(lambda params: stock.get_meta())
inventory_kpi = _json(stock.get_kpi)
inventory_by_sku = _json(stock.get_by_sku)
inventory_top_sku = _json(stock.get_top_sku)
inventory_by_warehouse = _json(stock.get_by_warehouse)
inventory_by_group = _json(stock.get_by_group)
inventory_by_location = _json(stock.get_by_location)

LOCATION_EXPORT_COLUMNS = [
    ExcelColumn('sku', 'Mã hàng', 14),
    ExcelColumn('item_name', 'Tên hàng', 60),
    ExcelColumn('whs', 'Kho', 10),
    ExcelColumn('whs_name', 'Tên kho', 32),
    ExcelColumn('status', 'Trạng thái', 12),
    ExcelColumn('qty', 'WMS', 12),
    ExcelColumn('uom', 'ĐVT', 8),
]


def inventory_by_location_export(request):
    rows = stock.export_by_location(request.GET)
    return excel_response(
        [ExcelSheet('Ton kho theo kho - trang thai', LOCATION_EXPORT_COLUMNS, rows)], 'ton_kho_theo_kho_va_trang_thai.xlsx'
    )


def inventory_export(request):
    warehouses, rows = stock.export_by_sku(request.GET)
    columns = [
        ExcelColumn('sku', 'SKU', 14),
        ExcelColumn('item_name', 'Tên sản phẩm', 60),
        ExcelColumn('uom', 'ĐVT', 8),
        ExcelColumn('total_qty', 'Tổng tồn', 12),
        ExcelColumn('available_qty', 'Khả dụng', 12),
        ExcelColumn('held_qty', 'Đang giữ', 12),
        *(ExcelColumn(w, w, 10) for w in warehouses),
    ]
    return excel_response([ExcelSheet('Ton kho theo SKU', columns, rows, freeze='D2')], 'ton_kho_theo_sku_va_kho.xlsx')


ecom_meta = _json(lambda params: ecom.get_meta())
ecom_kpi = _json(ecom.get_kpi)
ecom_daily = _json(ecom.get_daily)
ecom_by_sale = _json(ecom.get_by_sale)
ecom_top_products = _json(ecom.get_top_products)


def _staff_only(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'Chỉ quản trị viên được cập nhật danh mục.'}, status=403)
    return None


@require_POST
def ecom_channels_refresh(request):
    denied = _staff_only(request)
    if denied:
        return denied
    try:
        if airflow.has_active_run(OMS_ORDERS_DAG_ID):
            return JsonResponse({'error': 'DAG đơn hàng OMS đang chạy, thử lại sau ít phút.'}, status=409)
        if airflow.has_active_run(OMS_SALES_CHANNELS_DAG_ID):
            return JsonResponse({'error': 'Đang cập nhật kênh bán, vui lòng chờ.'}, status=409)
        run = airflow.trigger_dag(OMS_SALES_CHANNELS_DAG_ID)
    except airflow.AirflowError as exc:
        return JsonResponse({'error': f'Không gọi được Airflow: {exc}'}, status=502)
    return JsonResponse({'run_id': run.get('dag_run_id'), 'state': run.get('state')})


@require_GET
def ecom_channels_refresh_status(request):
    denied = _staff_only(request)
    if denied:
        return denied
    run_id = (request.GET.get('run_id') or '').strip()
    if not run_id:
        return JsonResponse({'error': 'Thiếu run_id'}, status=400)
    try:
        state = airflow.get_dag_run(OMS_SALES_CHANNELS_DAG_ID, run_id).get('state')
    except airflow.AirflowError as exc:
        return JsonResponse({'error': str(exc)}, status=502)
    if state == 'success':
        invalidate_source('oms_sales_channels')
    return JsonResponse({'state': state})
