from __future__ import annotations

import datetime as dt
import json
from functools import wraps

from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from ..core.excel import XLSX_CONTENT_TYPE, ExcelColumn, ExcelSheet, excel_response
from ..messaging import importer, provider, sample_file, sending, templates
from ..messaging.values import OWNERS, MessagingError, normalize_key


def _api(fn):
    @wraps(fn)
    def view(request, *args, **kwargs):
        try:
            return fn(request, *args, **kwargs)
        except MessagingError as exc:
            return JsonResponse({'error': str(exc)}, status=400)

    return view


def _body(request) -> dict:
    try:
        data = json.loads(request.body or b'{}')
    except ValueError as exc:
        raise MessagingError('Dữ liệu gửi lên không hợp lệ.') from exc
    if not isinstance(data, dict):
        raise MessagingError('Dữ liệu gửi lên không hợp lệ.')
    return data


def _int(value, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise MessagingError(f'Thiếu {field}.') from exc


def _staff_only(fn):
    @wraps(fn)
    def view(request, *args, **kwargs):
        if not request.user.is_staff:
            return JsonResponse({'error': 'Chỉ quản trị viên được tạo / sửa mẫu tin.'}, status=403)
        return fn(request, *args, **kwargs)

    return view


@require_GET
def template_editor(request, template_id: int | None = None):
    if template_id is None and not request.user.is_staff:
        return redirect('zns-templates')
    return render(request, 'messaging/template_edit.html', {'template_id': template_id or ''})


@require_GET
@_api
def template_list(request):
    owner = request.GET.get('owner') or None
    if owner and owner not in OWNERS:
        owner = None
    active_only = request.GET.get('active') == '1'
    return JsonResponse(
        {'data': templates.list_templates(owner, active_only), 'defaults': templates.DEFAULT_VARIABLES, 'default_content': templates.DEFAULT_CONTENT}
    )


VN_OFFSET = dt.timedelta(hours=7)


def _vn_time(value: str | None) -> str | None:
    if not value:
        return None
    return (dt.datetime.fromisoformat(value.rstrip('Z')) + VN_OFFSET).strftime('%d/%m/%Y %H:%M')


@require_GET
@_api
def template_export(request):
    owner = request.GET.get('owner') or None
    status = request.GET.get('status', '')
    query = normalize_key(request.GET.get('q', ''))
    rows = []
    for t in templates.list_templates(owner if owner in OWNERS else None):
        if status in ('0', '1') and t['is_active'] != (status == '1'):
            continue
        if query and query not in normalize_key(f"{t['name']} {t['zns_code']}"):
            continue
        rows.append(
            {
                **t,
                'status_label': 'Hoạt động' if t['is_active'] else 'Ngừng hoạt động',
                'created_vn': _vn_time(t['created_at']),
                'updated_vn': _vn_time(t['updated_at']),
            }
        )
    columns = [
        ExcelColumn('zns_code', 'Mã', 14),
        ExcelColumn('name', 'Tên', 32),
        ExcelColumn('owner', 'Chủ hàng', 10),
        ExcelColumn('variable_count', 'Số biến', 9),
        ExcelColumn('message_count', 'Số lượng', 10),
        ExcelColumn('batch_count', 'Số lô gửi', 10),
        ExcelColumn('status_label', 'Trạng thái', 16),
        ExcelColumn('created_vn', 'Ngày tạo', 18),
        ExcelColumn('created_by', 'Người tạo', 14),
        ExcelColumn('updated_vn', 'Ngày cập nhật', 18),
        ExcelColumn('updated_by', 'Người cập nhật', 14),
    ]
    return excel_response([ExcelSheet('Mẫu tin nhắn', columns, rows)], 'danh_sach_mau_tin.xlsx')


@require_POST
@_staff_only
@_api
def template_import(request):
    upload = request.FILES.get('file')
    if not upload:
        raise MessagingError('Vui lòng chọn file Excel.')
    return JsonResponse(importer.parse_template_workbook(upload))


@require_GET
@_api
def template_detail(request, template_id: int):
    return JsonResponse(templates.get_template(template_id))


@require_POST
@_staff_only
@_api
def template_save(request):
    template_id = templates.save_template(_body(request), request.user.get_username())
    return JsonResponse(templates.get_template(template_id))


@require_POST
@_staff_only
@_api
def template_active(request, template_id: int):
    templates.set_active(template_id, bool(_body(request).get('active')), request.user.get_username())
    return JsonResponse({'ok': True})


def _workbook_response(wb, filename: str) -> HttpResponse:
    response = HttpResponse(content_type=XLSX_CONTENT_TYPE)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@require_GET
@_api
def template_sample(request):
    return _workbook_response(*sample_file.template_sample_workbook())


@require_GET
@_api
def send_sample(request):
    return _workbook_response(*sample_file.sample_workbook())


@require_POST
@_api
def send_upload(request):
    upload = request.FILES.get('file')
    if not upload:
        raise MessagingError('Vui lòng chọn file Excel.')
    parsed = sending.parse_workbook(upload)
    batch_id = sending.create_draft(parsed, upload.name, request.user.get_username())
    return JsonResponse(
        {
            'batch_id': batch_id,
            'file_name': upload.name,
            'sheet': parsed['sheet'],
            'columns': parsed['columns'],
            'total_rows': len(parsed['rows']),
            'preview': parsed['rows'][: sending.PREVIEW_ROWS],
            'fixed_found': sorted(k for k in parsed['fixed'] if k != sending.TEMPLATE_CODE_KEY),
            'template_code': None if parsed['fixed'].get(sending.TEMPLATE_CODE_KEY) is None else str(parsed['fixed'][sending.TEMPLATE_CODE_KEY]).strip(),
        }
    )


def _send_args(request) -> tuple[int, int, dict, dict]:
    data = _body(request)
    return _int(data.get('batch_id'), 'file upload'), _int(data.get('template_id'), 'mẫu tin'), data.get('mapping'), data.get('fixed')


@require_POST
@_api
def send_evaluate(request):
    return JsonResponse(sending.evaluate(*_send_args(request)))


@require_POST
@_api
def send_confirm(request):
    return JsonResponse(sending.confirm(*_send_args(request), request.user.get_username()))


@require_GET
@_api
def _page(request) -> int:
    try:
        return int(request.GET.get('page') or 1)
    except ValueError:
        return 1


@require_GET
@_api
def batch_list(request):
    mode = provider.send_mode()
    return JsonResponse({**sending.list_batches(_page(request)), 'send_mode': mode, 'send_mode_label': sending.SEND_MODE_LABELS[mode]})


@require_GET
@_api
def batch_detail(request, batch_id: int):
    return JsonResponse(sending.batch_detail(batch_id, _page(request)))


@require_POST
@_api
def batch_cancel(request, batch_id: int):
    sending.cancel_batch(batch_id, request.user.get_username(), request.user.is_staff)
    return JsonResponse({'ok': True})


@require_GET
@_api
def batch_export(request, batch_id: int):
    batch, recipients = sending.batch_export_rows(batch_id)
    columns = [
        ExcelColumn('row_no', 'Dòng Excel', 10),
        ExcelColumn('customer', 'Tên khách hàng', 28),
        ExcelColumn('phone', 'Số điện thoại', 16),
        ExcelColumn('status_label', 'Trạng thái gửi', 20),
        ExcelColumn('error', 'Lỗi', 36),
        ExcelColumn('content', 'Nội dung', 80),
    ]
    return excel_response([ExcelSheet('Danh sách gửi', columns, recipients)], f'lo_gui_{batch["id"]}_{batch["zns_code"] or ""}.xlsx')
