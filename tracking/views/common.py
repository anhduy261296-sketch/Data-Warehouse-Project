from __future__ import annotations

import json
from functools import wraps

from django.http import JsonResponse
from django.shortcuts import redirect, render

from .. import access

from ..core.cache import cache_key, cached_call, get_or_set
from ..core.datatables import DetailReportConfig, export_detail_report_rows, paging_params, run_detail_report
from ..core.excel import ExcelColumn, ExcelSheet, excel_response
from ..core.sql import retry_on_deadlock
from ..messaging.values import MessagingError


def api_view(fn):
    """API trả lỗi nghiệp vụ thành JSON 400. GET chỉ đọc nên chạy lại được khi gặp deadlock."""
    read = retry_on_deadlock(fn)

    @wraps(fn)
    def view(request, *args, **kwargs):
        try:
            return (read if request.method == 'GET' else fn)(request, *args, **kwargs)
        except MessagingError as exc:
            return JsonResponse({'error': str(exc)}, status=400)

    return view


def json_body(request) -> dict:
    try:
        data = json.loads(request.body or b'{}')
    except ValueError as exc:
        raise MessagingError('Dữ liệu gửi lên không hợp lệ.') from exc
    if not isinstance(data, dict):
        raise MessagingError('Dữ liệu gửi lên không hợp lệ.')
    return data


def table_params(request) -> dict[str, int]:
    return paging_params(request.GET)


def home(request):
    return redirect(access.first_allowed_route(request.user) or 'no-access')


def no_access(request):
    return render(request, 'no_access.html')


def page_view(template_name: str):

    def view(request):
        return render(request, template_name)

    view.__name__ = f'page:{template_name}'
    return view


_PAGING_PARAMS = ('start', 'length', 'draw')


def _count_params(params) -> dict:
    return {k: params.getlist(k) for k in params if k not in _PAGING_PARAMS and not k.startswith(('order[', 'columns['))}


def datatable_report_view(config: DetailReportConfig, name: str):

    def view(request):
        if not config.cache_sources:
            return JsonResponse(run_detail_report(config, request.GET))

        def counts(produce):
            return get_or_set(cache_key(f'{name}:counts', config.cache_sources, _count_params(request.GET)), produce)

        return JsonResponse(cached_call(name, config.cache_sources, lambda: run_detail_report(config, request.GET, counts), request.GET))

    return view


def datatable_export_view(config: DetailReportConfig, filename: str):
    columns = [ExcelColumn(c.data_key, c.title or c.data_key) for c in config.columns]

    def view(request):
        rows = export_detail_report_rows(config, request.GET)
        return excel_response([ExcelSheet('Data', columns, rows, freeze=None)], filename)

    return view
