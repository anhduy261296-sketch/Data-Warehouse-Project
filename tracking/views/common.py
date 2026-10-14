"""View dung chung: trang HTML, API bang DataTables (DetailReportConfig), xuat Excel cua bang do."""

from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import render

from ..core.datatables import DetailReportConfig, export_detail_report_rows, run_detail_report
from ..core.excel import ExcelColumn, ExcelSheet, excel_response


def page_view(template_name: str):
    """Trang chi render template (du lieu do JS goi API)."""

    def view(request):
        return render(request, template_name)

    view.__name__ = f'page:{template_name}'
    return view


def datatable_report_view(config: DetailReportConfig):
    """API DataTables server-side cho 1 bang."""

    def view(request):
        return JsonResponse(run_detail_report(config, request.GET))

    return view


def datatable_export_view(config: DetailReportConfig, filename: str):
    """Xuat Excel 1 sheet 'Data' theo dung bo loc cua bang (toi da EXPORT_MAX_ROWS dong)."""
    columns = [ExcelColumn(c.data_key, c.title or c.data_key) for c in config.columns]

    def view(request):
        rows = export_detail_report_rows(config, request.GET)
        return excel_response([ExcelSheet('Data', columns, rows, freeze=None)], filename)

    return view
