from __future__ import annotations

import datetime as dt

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from ..access import department_options, zns_actor
from ..constants import EXPORT_MAX_ROWS
from ..core import audit
from ..core.excel import ExcelColumn, ExcelSheet, excel_response, workbook_response
from ..messaging import importer, logs, provider, sample_file, sending, templates
from ..messaging.values import OWNERS, MessagingError, normalize_key
from .common import api_view, json_body, table_params


def _int(value, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise MessagingError(f'Thiếu {field}.') from exc


APPROVAL_LABELS = {'pending': 'Chờ duyệt', 'approved': 'Đã duyệt', 'rejected': 'Từ chối'}


def _actor(request):
    return zns_actor(request.user)


def _with_review(template: dict, actor) -> dict:
    template['approval_label'] = APPROVAL_LABELS.get(template['approval_status'], template['approval_status'])
    template['can_approve'] = template['approval_status'] == 'pending' and actor.can_approve_template(template['owner'], template['department_id'])
    return template


def _check_owner(request, owner: str | None) -> None:
    if owner not in _actor(request).owners:
        raise MessagingError(f'Bạn chưa được phân quyền chủ hàng {owner or ""}.'.strip())


def _check_template_scope(request, template: dict) -> None:
    _check_owner(request, template['owner'])
    if not _actor(request).in_department(template['department_id']):
        raise MessagingError('Không tìm thấy mẫu tin.')


def _chosen_department(request, payload: dict, current: int | None = None) -> int:
    """Phòng ban của mẫu: chỉ được chọn phòng mình thuộc. Thuộc đúng một phòng thì tự điền khi tạo mới."""
    options = [d['id'] for d in department_options(request.user)]
    chosen = payload.get('department_id') or current
    if not chosen and len(options) == 1:
        chosen = options[0]
    if not chosen:
        raise MessagingError('Vui lòng chọn phòng ban của mẫu tin.' if options else 'Bạn chưa thuộc phòng ban nào nên chưa tạo được mẫu tin.')
    chosen = _int(chosen, 'phòng ban')
    if chosen not in options:
        raise MessagingError('Bạn không thuộc phòng ban đã chọn.')
    return chosen


@require_GET
def template_editor(request, template_id: int | None = None):
    return render(request, 'messaging/template_edit.html', {'template_id': template_id or ''})


@require_GET
@api_view
def template_list(request):
    owner = request.GET.get('owner') or None
    if owner and owner not in OWNERS:
        owner = None
    sendable_only = request.GET.get('active') == '1'
    actor = _actor(request)
    return JsonResponse(
        {'data': [_with_review(t, actor) for t in templates.list_templates(owner, sendable_only) if t['owner'] in actor.owners and actor.in_department(t['department_id'])],
         'departments': department_options(request.user), 'defaults': templates.DEFAULT_VARIABLES, 'default_content': templates.DEFAULT_CONTENT}
    )


VN_OFFSET = dt.timedelta(hours=7)


def _vn_time(value: str | None) -> str | None:
    if not value:
        return None
    return (dt.datetime.fromisoformat(value.rstrip('Z')) + VN_OFFSET).strftime('%d/%m/%Y %H:%M')


@require_GET
@api_view
def template_export(request):
    owner = request.GET.get('owner') or None
    status = request.GET.get('status', '')
    approval = request.GET.get('approval', '')
    query = normalize_key(request.GET.get('q', ''))
    rows = []
    actor = _actor(request)
    for t in templates.list_templates(owner if owner in OWNERS else None):
        if t['owner'] not in actor.owners or not actor.in_department(t['department_id']):
            continue
        if status in ('0', '1') and t['is_active'] != (status == '1'):
            continue
        if approval in APPROVAL_LABELS and t['approval_status'] != approval:
            continue
        if query and query not in normalize_key(f"{t['name']} {t['zns_code']}"):
            continue
        rows.append(
            {
                **t,
                'status_label': 'Hoạt động' if t['is_active'] else 'Ngừng hoạt động',
                'approval_label': APPROVAL_LABELS.get(t['approval_status'], t['approval_status']),
                'created_vn': _vn_time(t['created_at']),
                'updated_vn': _vn_time(t['updated_at']),
            }
        )
    audit.log('template.export', request.user.get_username(), 'template', None, f'{len(rows)} mẫu')
    columns = [
        ExcelColumn('zns_code', 'Mã', 14),
        ExcelColumn('name', 'Tên', 32),
        ExcelColumn('owner', 'Chủ hàng', 10),
        ExcelColumn('department_name', 'Phòng ban', 14),
        ExcelColumn('variable_count', 'Số biến', 9),
        ExcelColumn('message_count', 'Số lượng', 10),
        ExcelColumn('batch_count', 'Số lô gửi', 10),
        ExcelColumn('approval_label', 'Duyệt', 12),
        ExcelColumn('status_label', 'Trạng thái', 16),
        ExcelColumn('created_vn', 'Ngày tạo', 18),
        ExcelColumn('created_by', 'Người tạo', 14),
        ExcelColumn('updated_vn', 'Ngày cập nhật', 18),
        ExcelColumn('updated_by', 'Người cập nhật', 14),
    ]
    return excel_response([ExcelSheet('Mẫu tin nhắn', columns, rows)], 'danh_sach_mau_tin.xlsx')


@require_POST
@api_view
def template_import(request):
    upload = request.FILES.get('file')
    if not upload:
        raise MessagingError('Vui lòng chọn file Excel.')
    parsed = importer.parse_template_workbook(upload)
    audit.log('template.import', request.user.get_username(), 'template', parsed.get('zns_code'), f'{upload.name} · {len(parsed["variables"])} biến')
    return JsonResponse(parsed)


def _template_payload(request, template_id: int) -> dict:
    template = templates.get_template(template_id)
    _check_template_scope(request, template)
    return _with_review(template, _actor(request))


@require_GET
@api_view
def template_detail(request, template_id: int):
    return JsonResponse(_template_payload(request, template_id))


@require_POST
@api_view
def template_save(request):
    payload = json_body(request)
    _check_owner(request, payload.get('owner'))
    current = None
    if payload.get('id'):
        existing = templates.get_template(_int(payload['id'], 'mẫu tin'))
        _check_template_scope(request, existing)
        current = existing['department_id']
    payload['department_id'] = _chosen_department(request, payload, current)
    template_id = templates.save_template(payload, request.user.get_username())
    return JsonResponse(_template_payload(request, template_id))


@require_POST
@api_view
def template_approve(request, template_id: int):
    templates.approve_template(template_id, _actor(request))
    return JsonResponse(_template_payload(request, template_id))


@require_POST
@api_view
def template_reject(request, template_id: int):
    templates.reject_template(template_id, json_body(request).get('reason'), _actor(request))
    return JsonResponse(_template_payload(request, template_id))


@require_POST
@api_view
def template_active(request, template_id: int):
    _check_template_scope(request, templates.get_template(template_id))
    templates.set_active(template_id, bool(json_body(request).get('active')), request.user.get_username())
    return JsonResponse({'ok': True})


@require_POST
@api_view
def template_delete(request, template_id: int):
    _check_template_scope(request, templates.get_template(template_id))
    templates.delete_template(template_id, request.user.get_username())
    return JsonResponse({'ok': True})


@require_GET
@api_view
def template_sample(request):
    return workbook_response(*sample_file.template_sample_workbook([d['name'] for d in department_options(request.user)]))


@require_GET
@api_view
def send_sample(request):
    return workbook_response(*sample_file.sample_workbook())


@require_POST
@api_view
def send_upload(request):
    upload = request.FILES.get('file')
    if not upload:
        raise MessagingError('Vui lòng chọn file Excel.')
    parsed = sending.parse_workbook(upload)
    batch_id = sending.create_draft(parsed, upload.name, request.user.get_username())
    audit.log('zns.upload', request.user.get_username(), 'batch', batch_id, f'{upload.name} · {len(parsed["rows"])} dòng')
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
    data = json_body(request)
    return _int(data.get('batch_id'), 'file upload'), _int(data.get('template_id'), 'mẫu tin'), data.get('mapping'), data.get('fixed')


@require_POST
@api_view
def send_evaluate(request):
    return JsonResponse(sending.evaluate(*_send_args(request), _actor(request)))


@require_POST
@api_view
def send_confirm(request):
    return JsonResponse(sending.confirm(*_send_args(request), _actor(request)))


@require_GET
@api_view
def batch_list(request):
    return JsonResponse({**sending.list_batches(**table_params(request), actor=_actor(request)), 'send_mode': provider.send_mode()})


@require_GET
@api_view
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
        ExcelColumn('duration_label', 'Duration', 10),
        ExcelColumn('created_by', 'Người tạo', 14),
    ]
    return excel_response([ExcelSheet('Lịch sử lô gửi', columns, rows)], 'lich_su_lo_gui.xlsx')


@require_GET
@api_view
def batch_detail(request, batch_id: int):
    return JsonResponse(sending.batch_detail(batch_id, _actor(request)))


@require_GET
@api_view
def batch_recipients(request, batch_id: int):
    return JsonResponse(sending.list_recipients(batch_id, _actor(request), status=request.GET.get('status'), **table_params(request)))


@require_GET
@api_view
def recipient_attempts(request, batch_id: int, recipient_id: int):
    return JsonResponse({'data': sending.recipient_attempts(batch_id, recipient_id, _actor(request))})


@require_POST
@api_view
def batch_skip(request, batch_id: int):
    data = json_body(request)
    return JsonResponse(sending.skip_recipients(batch_id, data.get('recipient_id'), data.get('reason'), _actor(request)))


@require_POST
@api_view
def batch_retry(request, batch_id: int):
    return JsonResponse(sending.retry_same_batch(batch_id, json_body(request).get('kinds'), _actor(request)))


@require_POST
@api_view
def batch_retry_new(request, batch_id: int):
    return JsonResponse(sending.retry_as_new_batch(batch_id, _actor(request)))


@require_POST
@api_view
def batch_cancel(request, batch_id: int):
    sending.cancel_batch(batch_id, _actor(request))
    return JsonResponse({'ok': True})


@require_GET
@api_view
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


@require_GET
def log_page(request):
    return render(request, 'messaging/logs.html', {'departments': department_options(request.user)})


@require_GET
@api_view
def log_list(request):
    params = table_params(request)
    total, data = logs.list_logs(request.GET, _actor(request), params['start'], params['length'])
    return JsonResponse({'draw': params['draw'], 'recordsTotal': total, 'recordsFiltered': total, 'data': data})


@require_GET
@api_view
def log_export(request):
    _, data = logs.list_logs(request.GET, _actor(request), 0, EXPORT_MAX_ROWS)
    audit.log('zns.log_export', request.user.get_username(), None, None, f'{len(data)} dòng')
    for r in data:
        r['created_vn'] = _vn_time(r['created_at'])
    columns = [
        ExcelColumn('created_vn', 'Thời gian', 18),
        ExcelColumn('actor', 'Người thực hiện', 18),
        ExcelColumn('action_label', 'Thao tác', 28),
        ExcelColumn('target_label', 'Đối tượng', 16),
        ExcelColumn('department_name', 'Phòng ban', 14),
        ExcelColumn('detail', 'Chi tiết', 80),
        ExcelColumn('ip_address', 'IP', 16),
    ]
    return excel_response([ExcelSheet('Nhật ký', columns, data)], 'nhat_ky_chien_dich.xlsx')
