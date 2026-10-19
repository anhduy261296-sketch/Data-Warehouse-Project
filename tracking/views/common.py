from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import render

from ..core.cache import cache_key, cached_call, get_or_set
from ..core.datatables import DetailReportConfig, export_detail_report_rows, run_detail_report
from ..core.excel import ExcelColumn, ExcelSheet, excel_response


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
