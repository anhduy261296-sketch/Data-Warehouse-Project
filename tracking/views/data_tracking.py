from __future__ import annotations

import re

from django.http import JsonResponse

from ..core.excel import ExcelColumn, ExcelSheet, excel_response
from ..queries.orders import RECON_CONFIGS
from ..core.datatables import get_distinct_so_status
from ..queries.recon_inventory import get_inventory_detail, get_inventory_diff_list, get_inventory_meta


def _col(key: str, header: str, width: float) -> ExcelColumn:
    return ExcelColumn(key, header, width, is_date=key.endswith('_date'))


DETAIL_EXPORT_SHEETS = (
    (
        'both',
        'Hai bên có',
        [
            _col('doc_no', 'Số chứng từ', 24),
            _col('wms_doc_no', 'Số chứng từ WMS', 24),
            _col('sap_date', 'Ngày', 12),
            _col('wms_date', 'Ngày WMS', 12),
            _col('doc_type', 'Loại', 30),
            _col('wms_doc_type', 'Loại WMS', 30),
            _col('sap_qty', 'SAP', 10),
            _col('wms_qty', 'WMS', 10),
            _col('diff_qty', 'Lệch', 10),
        ],
    ),
    (
        'sap_only',
        'SAP có WMS không',
        [
            _col('doc_no', 'Số chứng từ', 24),
            _col('doc_date', 'Ngày chứng từ', 14),
            _col('doc_type', 'Loại', 30),
            _col('qty', 'SL (+/-)', 10),
        ],
    ),
    (
        'wms_only',
        'WMS có SAP không',
        [
            _col('doc_no', 'Số chứng từ', 24),
            _col('doc_date', 'Ngày chứng từ', 14),
            _col('doc_type', 'Loại', 30),
            _col('qty', 'SL (+/-)', 10),
        ],
    ),
)
_ITEM_COLUMNS = [
    _col('item_code', 'Mã hàng', 14),
    _col('item_name', 'Tên hàng', 50),
    _col('whs_code', 'Kho', 10),
    _col('status_item', 'Trạng thái', 14),
]
DIFF_EXPORT_SHEETS = (
    ('both', 'Hai bên có', [*_ITEM_COLUMNS, _col('sap_qty', 'SAP', 12), _col('wms_qty', 'WMS', 12), _col('diff_qty', 'Lệch', 12)]),
    ('sap_only', 'SAP có WMS không', [*_ITEM_COLUMNS, _col('sap_qty', 'SL', 12)]),
    ('wms_only', 'WMS có SAP không', [*_ITEM_COLUMNS, _col('wms_qty', 'SL', 12)]),
)


def _inventory_workbook(sheets, data, filename):
    return excel_response([ExcelSheet(title, columns, data[key], total_label='Tổng') for key, title, columns in sheets], filename)


def _detail_params(request):
    item_code = (request.GET.get('item_code') or '').strip()
    whs_code = (request.GET.get('whs_code') or '').strip()
    status_item = (request.GET.get('status_item') or '').strip()
    return item_code, whs_code, status_item


def recon_wrt_so_status_options(request):
    return JsonResponse({'options': get_distinct_so_status(RECON_CONFIGS['wrt'])})


def recon_inventory_meta(request):
    return JsonResponse(get_inventory_meta())


def recon_inventory_detail(request):
    item_code, whs_code, status_item = _detail_params(request)
    if not item_code or not whs_code:
        return JsonResponse({'error': 'Thieu item_code hoac whs_code'}, status=400)
    return JsonResponse(get_inventory_detail(item_code, whs_code, status_item))


def recon_inventory_detail_export(request):
    item_code, whs_code, status_item = _detail_params(request)
    if not item_code or not whs_code:
        return JsonResponse({'error': 'Thieu item_code hoac whs_code'}, status=400)
    safe = re.sub(r'[^A-Za-z0-9_-]', '', f'{item_code}_{whs_code}_{status_item}'.strip('_'))
    return _inventory_workbook(
        DETAIL_EXPORT_SHEETS, get_inventory_detail(item_code, whs_code, status_item), f'chi_tiet_ton_kho_{safe}.xlsx'
    )


def recon_inventory_diff_list(request):
    return JsonResponse(get_inventory_diff_list())


def recon_inventory_diff_export(request):
    return _inventory_workbook(DIFF_EXPORT_SHEETS, get_inventory_diff_list(), 'ton_kho_lech_sap_wms.xlsx')
