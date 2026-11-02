from __future__ import annotations

import datetime as dt
import json
from functools import wraps

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from ..access import zns_actor
from ..constants import EXPORT_MAX_ROWS, MAX_PAGE_LENGTH
from ..core import audit
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


def _actor(request):
    return zns_actor(request.user)


def _check_owner(request, owner: str | None) -> None:
    if owner not in _actor(request).owners:
        raise MessagingError(f'Bạn chưa được phân quyền chủ hàng {owner or ""}.'.strip())


@require_GET
def template_editor(request, template_id: int | None = None):
    return render(request, 'messaging/template_edit.html', {'template_id': template_id or ''})


@require_GET
@_api
def template_list(request):
    owner = request.GET.get('owner') or None
    if owner and owner not in OWNERS:
        owner = None
    active_only = request.GET.get('active') == '1'
    owners = _actor(request).owners
    return JsonResponse(
        {'data': [t for t in templates.list_templates(owner, active_only) if t['owner'] in owners], 'defaults': templates.DEFAULT_VARIABLES, 'default_content': templates.DEFAULT_CONTENT}
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
    owners = _actor(request).owners
    for t in templates.list_templates(owner if owner in OWNERS else None):
        if t['owner'] not in owners:
            continue
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
@_api
def template_import(request):
    upload = request.FILES.get('file')
    if not upload:
        raise MessagingError('Vui lòng chọn file Excel.')
    return JsonResponse(importer.parse_template_workbook(upload))


@require_GET
@_api
def template_detail(request, template_id: int):
    template = templates.get_template(template_id)
    _check_owner(request, template['owner'])
    return JsonResponse(template)


@require_POST
@_api
def template_save(request):
    payload = _body(request)
    _check_owner(request, payload.get('owner'))
    if payload.get('id'):
        _check_owner(request, templates.get_template(int(payload['id']))['owner'])
    template_id = templates.save_template(payload, request.user.get_username())
    return JsonResponse(templates.get_template(template_id))


@require_POST
@_api
def template_active(request, template_id: int):
    _check_owner(request, templates.get_template(template_id)['owner'])
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
    return JsonResponse(sending.evaluate(*_send_args(request), _actor(request)))


@require_POST
@_api
def send_confirm(request):
    return JsonResponse(sending.confirm(*_send_args(request), _actor(request)))


def _table_params(request) -> dict[str, int]:
    def number(name: str, default: int) -> int:
        try:
            return int(request.GET.get(name) or default)
        except ValueError:
            return default

    length = number('length', 10)
    return {
        'draw': number('draw', 1),
        'start': max(number('start', 0), 0),
        'length': min(length, MAX_PAGE_LENGTH) if length > 0 else MAX_PAGE_LENGTH,
    }


@require_GET
@_api
def batch_list(request):
    mode = provider.send_mode()
    return JsonResponse({**sending.list_batches(**_table_params(request), actor=_actor(request)), 'send_mode': mode, 'send_mode_label': sending.SEND_MODE_LABELS[mode]})


@require_GET
@_api
def batch_list_export(request):
    rows = sending.list_batches(0, 0, EXPORT_MAX_ROWS, _actor(request))['data']
    audit.log('zns.export_history', request.user.get_username(), 'batch', None, f'{len(rows)} lô')
    for r in rows:
        r['confirmed_vn'] = _vn_time(r['confirmed_at'])
    columns = [
        ExcelColumn('id', 'Lô', 8),
        ExcelColumn('parent_batch_id', 'Gửi lại từ lô', 12),
        ExcelColumn('confirmed_vn', 'Xác nhận lúc', 18),
        ExcelColumn('template_name', 'Mẫu tin', 28),
        ExcelColumn('zns_code', 'Mã mẫu', 14),
        ExcelColumn('owner', 'Chủ hàng', 10),
        ExcelColumn('file_name', 'File', 32),
        ExcelColumn('total_rows', 'Tổng', 9),
        ExcelColumn('valid_rows', 'Hợp lệ', 9),
        ExcelColumn('invalid_rows', 'Lỗi', 9),
        ExcelColumn('status_label', 'Trạng thái', 16),
        ExcelColumn('sent_rows', 'Đã gửi', 9),
        ExcelColumn('failed_rows', 'Gửi lỗi', 9),
        ExcelColumn('unknown_rows', 'Chưa rõ', 9),
        ExcelColumn('skipped_rows', 'Bỏ qua', 9),
        ExcelColumn('created_by', 'Người tạo', 14),
    ]
    return excel_response([ExcelSheet('Lịch sử lô gửi', columns, rows)], 'lich_su_lo_gui.xlsx')


@require_GET
@_api
def batch_detail(request, batch_id: int):
    return JsonResponse(sending.batch_detail(batch_id, _actor(request)))


@require_GET
@_api
def batch_recipients(request, batch_id: int):
    return JsonResponse(sending.list_recipients(batch_id, _actor(request), status=request.GET.get('status'), **_table_params(request)))


@require_GET
@_api
def recipient_attempts(request, batch_id: int, recipient_id: int):
    return JsonResponse({'data': sending.recipient_attempts(batch_id, recipient_id, _actor(request))})


@require_POST
@_api
def batch_skip(request, batch_id: int):
    data = _body(request)
    return JsonResponse(sending.skip_recipients(batch_id, data.get('recipient_id'), data.get('reason'), _actor(request)))


@require_POST
@_api
def batch_retry(request, batch_id: int):
    return JsonResponse(sending.retry_same_batch(batch_id, _body(request).get('kinds'), _actor(request)))


@require_POST
@_api
def batch_retry_new(request, batch_id: int):
    return JsonResponse(sending.retry_as_new_batch(batch_id, _actor(request)))


@require_POST
@_api
def batch_approve(request, batch_id: int):
    return JsonResponse(sending.approve_batch(batch_id, _actor(request)))


@require_POST
@_api
def batch_reject(request, batch_id: int):
    sending.reject_batch(batch_id, _body(request).get('reason'), _actor(request))
    return JsonResponse({'ok': True})


@require_POST
@_api
def batch_cancel(request, batch_id: int):
    sending.cancel_batch(batch_id, _actor(request))
    return JsonResponse({'ok': True})


@require_GET
@_api
def batch_export(request, batch_id: int):
    status = request.GET.get('status')
    batch, recipients = sending.batch_export_rows(batch_id, status, _actor(request))
    audit.log('zns.export', request.user.get_username(), 'batch', batch_id, f'{len(recipients)} khách{f", lọc {status}" if status else ""}')
    columns = [
        ExcelColumn('row_no', 'Dòng Excel', 10),
        ExcelColumn('customer', 'Tên khách hàng', 28),
        ExcelColumn('phone', 'Số điện thoại', 16),
        ExcelColumn('status_label', 'Trạng thái gửi', 20),
        ExcelColumn('error_kind_label', 'Loại lỗi', 18),
        ExcelColumn('attempt_count', 'Số lần thử', 10),
        ExcelColumn('error', 'Lỗi', 36),
        ExcelColumn('skip_reason', 'Lý do bỏ qua', 30),
        ExcelColumn('content', 'Nội dung', 80),
    ]
    return excel_response([ExcelSheet('Danh sách gửi', columns, recipients)], f'lo_gui_{batch["id"]}_{status + "_" if status else ""}{batch["zns_code"] or ""}.xlsx')
