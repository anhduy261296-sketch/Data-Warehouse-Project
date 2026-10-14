"""Menu Bao cao > Ton kho: API tung vung + xuat Excel. (Bao cao DH theo NV dung view chung - xem tracking/urls.py.)"""

from __future__ import annotations

from django.http import JsonResponse

from ..core.excel import ExcelColumn, ExcelSheet, excel_response
from ..reports import stock


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
