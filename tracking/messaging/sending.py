from __future__ import annotations

import json
import logging
import random
import threading
import time
import uuid
from typing import Any

import openpyxl
from django.db import connection, transaction

from ..constants import (
    ZNS_MAX_AUTO_RESUMES,
    ZNS_MAX_MANUAL_RETRIES,
    ZNS_PAUSE_AFTER,
    ZNS_PAUSE_AFTER_ERRORS,
    ZNS_RESUME_AFTER_SECONDS,
    ZNS_RESUME_MAX_SECONDS,
    ZNS_RETRY_DELAYS,
    ZNS_SEND_DELAY_MS,
    ZNS_WATCH_INTERVAL_SECONDS,
)
from ..core import audit
from ..core.sql import retry_on_deadlock, rows
from . import provider
from .templates import load_template
from .values import (
    PHONE_KEYS,
    iso_utc,
    MessagingError,
    cell_value,
    coerce,
    display,
    normalize_key,
    normalize_phone,
    render,
    to_json,
)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
PREVIEW_ROWS = 20
DRAFT_TTL_HOURS = 24
MAX_SQL_PARAMS = 2000
SEND_CHUNK = 50
# Ép dùng index: lô lớn SQL Server hay chọn sort, thiếu RAM thì sort phải xếp hàng chờ bộ nhớ tới 25 giây.
_BATCH_ROW_INDEX = 'IX_ZnsSendRecipients_BatchRow'
logger = logging.getLogger(__name__)
_FIXED_KEY_HEADERS = frozenset({'biencodinh', 'bien', 'tenbien', 'variable', 'key'})
_FIXED_VALUE_HEADERS = frozenset({'dulieu', 'giatri', 'value', 'noidung'})
TEMPLATE_CODE_KEY = 'templatecode'
STATUS_LABELS = {
    'draft': 'Nháp',
    'pending': 'Chờ gửi',
    'pending_approval': 'Chờ duyệt',
    'rejected': 'Từ chối',
    'sending': 'Đang gửi',
    'done': 'Đã gửi',
    'cancelled': 'Đã hủy',
    'invalid': 'Lỗi dữ liệu',
    'sent': 'Thành công',
    'failed': 'Thất bại',
    'unknown': 'Chưa rõ',
    'skipped': 'Bỏ qua',
    'simulated': 'Chạy thử',
}
BATCH_STATUS_LABELS = {**STATUS_LABELS, 'paused': 'Tạm dừng', 'partial': 'Gửi một phần'}
ATTEMPT_RESULT_LABELS = {
    'sent': 'Thành công',
    'simulated': 'Chạy thử',
    'temporary': 'Lỗi tạm thời',
    'unknown': 'Chưa rõ kết quả',
    'config': 'Lỗi cấu hình',
    'business': 'Incom từ chối',
}
ERROR_KIND_LABELS = {'temporary': 'Lỗi tạm thời', 'unknown': 'Chưa rõ kết quả', 'config': 'Lỗi cấu hình', 'business': 'Incom từ chối'}
SKIPPABLE = ('partial', 'failed', 'paused')
_SKIP_CLAUSE = "Status IN ('failed', 'unknown') AND RetriedInBatchId IS NULL"
CANCELLABLE = ('pending', 'sending', 'paused')
RECIPIENT_FILTERS = {
    'sent': "Status IN ('sent', 'simulated')",
    'failed': "Status = 'failed'",
    'unknown': "Status = 'unknown'",
    'invalid': "Status = 'invalid'",
    'errors': "Status IN ('failed', 'unknown', 'invalid')",
    'skipped': "Status = 'skipped'",
    'waiting': "Status IN ('pending', 'sending')",
    'cancelled': "Status = 'cancelled'",
}
_NEW_BATCH_CLAUSE = "(Status = 'failed' AND ErrorKind = 'config') OR Status = 'pending'"


def _duration_label(milliseconds: int | None, seconds: int | None) -> str | None:
    if milliseconds is None:
        # Lô cũ chỉ lưu đến giây.
        return '<1s' if seconds == 0 else None
    if milliseconds < 1000:
        return f'{milliseconds}ms'
    minutes, rest = divmod(milliseconds // 1000, 60)
    return f'{minutes}m{rest}s' if minutes else f'{rest}s'


def _status_label(status: str, send_mode: str | None) -> str:
    if status == 'done' and send_mode == 'dry_run':
        return 'Đã chạy thử'
    return BATCH_STATUS_LABELS.get(status, status)


def read_sheet_rows(ws) -> list[tuple[int, list[Any]]]:
    out = []
    for idx, row in enumerate(ws.iter_rows(), start=1):
        cells = [cell_value(c.value, getattr(c, 'number_format', None)) for c in row]
        if any(c is not None for c in cells):
            out.append((idx, cells))
        if len(out) > MAX_ROWS + 100:
            break
    return out


def _fixed_block(sheet_rows: list[tuple[int, list[Any]]]) -> tuple[dict[str, Any], set[int], tuple[int, int] | None]:
    for pos, (_, cells) in enumerate(sheet_rows):
        keys = [normalize_key(c) for c in cells]
        key_col = next((i for i, k in enumerate(keys) if k in _FIXED_KEY_HEADERS), None)
        if key_col is None:
            continue
        value_col = next((i for i in range(key_col + 1, len(keys)) if keys[i] in _FIXED_VALUE_HEADERS), None)
        if value_col is None:
            continue
        fixed, used = {}, {sheet_rows[pos][0]}
        previous = sheet_rows[pos][0]
        for row_no, row in sheet_rows[pos + 1 :]:
            name = row[key_col] if key_col < len(row) else None
            # Dòng trống cũng là hết bảng: read_sheet_rows bỏ dòng trống nên phải so số dòng.
            if name is None or row_no != previous + 1:
                break
            previous = row_no
            fixed[normalize_key(name)] = row[value_col] if value_col < len(row) else None
            used.add(row_no)
        return fixed, used, (key_col, value_col)
    return {}, set(), None


def _beside_block(sheet_rows: list[tuple[int, list[Any]]], block: tuple[int, int]) -> list[tuple[int, list[Any]]] | None:
    """Bảng khách nằm cạnh bảng biến cố định (dùng chung số dòng): trả về các dòng chỉ còn phần bảng khách."""
    key_col, value_col = block
    for _, cells in sheet_rows[:30]:
        phones = [i for i, c in enumerate(cells) if normalize_key(c) in PHONE_KEYS]
        if phones and phones[0] > value_col:
            return [(n, [None] * (value_col + 1) + c[value_col + 1 :]) for n, c in sheet_rows]
        if phones and all(i < key_col for i in phones):
            return [(n, c[:key_col]) for n, c in sheet_rows]
    return None


def _customer_table(sheet_rows: list[tuple[int, list[Any]]], skip: set[int], block: tuple[int, int] | None = None) -> tuple[list[str], list[dict]] | None:
    beside = _beside_block(sheet_rows, block) if block else None
    candidates = beside if beside is not None else [(n, c) for n, c in sheet_rows if n not in skip]
    header_pos = next((i for i, (_, c) in enumerate(candidates[:30]) if any(normalize_key(x) in PHONE_KEYS for x in c)), None)
    if header_pos is None:
        return None
    _, header = candidates[header_pos]
    first = next(i for i, h in enumerate(header) if h is not None) if beside is not None else 0
    last = max(i for i, h in enumerate(header) if h is not None)
    columns = [str(h) if h is not None else f'Cột {i + 1}' for i, h in enumerate(header[first : last + 1], start=first)]
    data = []
    for row_no, cells in candidates[header_pos + 1 :]:
        values = (cells[first:] + [None] * len(columns))[: len(columns)]
        if any(v is not None for v in values):
            data.append({'row_no': row_no, 'values': values})
    return columns, data


def open_workbook(upload: Any) -> openpyxl.Workbook:
    if upload.size > MAX_UPLOAD_BYTES:
        raise MessagingError(f'File quá lớn (tối đa {MAX_UPLOAD_BYTES // 1024 // 1024} MB).')
    if not upload.name.lower().endswith(('.xlsx', '.xlsm')):
        raise MessagingError('Chỉ hỗ trợ file Excel .xlsx.')
    try:
        return openpyxl.load_workbook(upload, read_only=True, data_only=True)
    except Exception as exc:
        raise MessagingError('Không đọc được file Excel.') from exc


def parse_workbook(upload: Any) -> dict[str, Any]:
    wb = open_workbook(upload)
    fixed: dict[str, Any] = {}
    table = None
    try:
        for ws in wb.worksheets:
            data_rows = read_sheet_rows(ws)
            block, used, block_cols = _fixed_block(data_rows)
            for key, value in block.items():
                fixed.setdefault(key, value)
            if table is None:
                found = _customer_table(data_rows, used, block_cols)
                if found:
                    table = (ws.title, *found)
    finally:
        wb.close()
    if table is None:
        raise MessagingError('Không tìm thấy bảng khách hàng: cần một dòng tiêu đề có cột "Số điện thoại".')
    sheet, columns, data = table
    if not data:
        raise MessagingError('Danh sách khách hàng đang trống.')
    if len(data) > MAX_ROWS:
        raise MessagingError(f'Tối đa {MAX_ROWS:,} khách hàng mỗi lần gửi.'.replace(',', '.'))
    return {'sheet': sheet, 'columns': columns, 'rows': data, 'fixed': fixed}


def create_draft(parsed: dict[str, Any], file_name: str, user: str) -> int:
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE dbo.ZnsSendBatches SET RawData = NULL WHERE Status = 'draft' AND RawData IS NOT NULL AND CreatedAt < DATEADD(HOUR, -{DRAFT_TTL_HOURS}, SYSUTCDATETIME())"
        )
        cursor.execute(
            """
            INSERT INTO dbo.ZnsSendBatches (FileName, RawData, TotalRows, Status, CreatedBy)
            OUTPUT INSERTED.Id VALUES (%s, %s, %s, 'draft', %s)
            """,
            [file_name[:255], json.dumps(parsed, ensure_ascii=False, default=str), len(parsed['rows']), user],
        )
        return int(cursor.fetchone()[0])


def _draft(cursor: Any, batch_id: int, username: str) -> dict[str, Any]:
    cursor.execute('SELECT Status, RawData, FileName, CreatedBy FROM dbo.ZnsSendBatches WHERE Id = %s', [batch_id])
    row = cursor.fetchone()
    if not row or row[3] != username:
        raise MessagingError('Không tìm thấy file đã upload, vui lòng upload lại.')
    if row[0] != 'draft':
        raise MessagingError('Danh sách này đã được xác nhận gửi trước đó.')
    if not row[1]:
        raise MessagingError('File upload đã hết hạn, vui lòng upload lại.')
    data = json.loads(row[1])
    data['file_name'] = row[2]
    return data


def _auto_mapping(variables: list[dict], columns: list[str]) -> dict[str, int | None]:
    keys = [normalize_key(c) for c in columns]
    mapping: dict[str, int | None] = {'__phone__': next((i for i, k in enumerate(keys) if k in PHONE_KEYS), None)}
    for v in variables:
        if v['source'] != 'customer':
            continue
        wanted = {normalize_key(v['name']), normalize_key(v['label'])} - {''}
        mapping[v['name']] = next((i for i, k in enumerate(keys) if k in wanted), None)
    if mapping.get('name') is None and any(v['name'] == 'name' and v['source'] == 'customer' for v in variables):
        mapping['name'] = next((i for i, k in enumerate(keys) if k in ('tenkhachhang', 'hoten', 'ten', 'khachhang', 'customername')), None)
    return mapping


def _clean_mapping(raw: Any, variables: list[dict], columns: list[str]) -> dict[str, int | None]:
    auto = _auto_mapping(variables, columns)
    if not isinstance(raw, dict):
        return auto
    mapping = {}
    for key in auto:
        value = raw.get(key, auto[key])
        try:
            index = int(value) if value not in (None, '') else None
        except (TypeError, ValueError):
            index = None
        mapping[key] = index if index is not None and 0 <= index < len(columns) else None
    return mapping


def _fixed_given(v: dict[str, Any], raw_fixed: dict[str, Any], excel_fixed: dict[str, Any]) -> Any:
    """Giá trị dùng chung của biến: nhập tay khi gửi, rồi đến dữ liệu của mẫu, rồi đến bảng biến cố định trong file."""
    for value in (raw_fixed.get(v['name']), v.get('default_value'), excel_fixed.get(normalize_key(v['name']))):
        if value is not None and str(value).strip():
            return value
    return None


def _customer_label(variables: list[dict], values: dict[str, Any]) -> str | None:
    if values.get('name'):
        return str(values['name'])
    first = next((v['name'] for v in variables if v['source'] == 'customer' and v['data_type'] == 'text' and values.get(v['name'])), None)
    return str(values[first]) if first else None


def _evaluate(cursor: Any, batch_id: int, template_id: int, raw_mapping: Any, raw_fixed: Any, actor: Any) -> dict[str, Any]:
    draft = _draft(cursor, batch_id, actor.username)
    template = load_template(cursor, template_id)
    if template['owner'] not in actor.owners:
        raise MessagingError(f'Bạn chưa được phân quyền chủ hàng {template["owner"]}.')
    if not actor.in_department(template['department_id']):
        raise MessagingError('Không tìm thấy mẫu tin.')
    if template['approval_status'] != 'approved':
        raise MessagingError('Mẫu tin chưa được duyệt, chưa dùng để gửi được.')
    if not template['is_active']:
        raise MessagingError('Mẫu tin đang ngừng hoạt động.')
    active = [v for v in template['variables'] if v['is_active']]
    columns = draft['columns']
    mapping = _clean_mapping(raw_mapping, active, columns)
    excel_fixed = draft.get('fixed') or {}
    raw_fixed = raw_fixed if isinstance(raw_fixed, dict) else {}

    # Incom báo thiếu tham số (-2) cả với biến không có trong nội dung, nên biến đang bật đều phải có dữ liệu.
    variables = [{**v, 'is_required': True} for v in active]
    template = {**template, 'variables': variables}

    fixed_values, fixed_display, fixed_input, fixed_errors = {}, {}, {}, {}
    for v in variables:
        if v['source'] != 'fixed':
            continue
        given = _fixed_given(v, raw_fixed, excel_fixed)
        value, error = coerce(v['data_type'], given)
        fixed_input[v['name']] = display(v['data_type'], value) if not error else str(given)
        if error or value is None:
            fixed_errors[v['name']] = error or 'Chưa có dữ liệu'
        fixed_values[v['name']] = value
        fixed_display[v['name']] = display(v['data_type'], value)

    mapping_errors = []
    if mapping['__phone__'] is None:
        mapping_errors.append('Chưa chọn cột Số điện thoại.')
    for v in variables:
        if v['source'] == 'customer' and mapping.get(v['name']) is None:
            mapping_errors.append(f'Biến <{v["name"]}> theo khách hàng: chọn cột từ Excel.')
    warnings = []
    excel_code = excel_fixed.get(TEMPLATE_CODE_KEY)
    if excel_code not in (None, '') and str(excel_code).strip() != str(template['zns_code']):
        warnings.append(f'File Excel ghi templatecode = {excel_code}, khác mã của mẫu đang chọn ({template["zns_code"]}).')

    results, seen_phones = [], {}
    for row in draft['rows']:
        cells = row['values']
        errors, values, shown = [], dict(fixed_values), dict(fixed_display)
        phone_col = mapping['__phone__']
        phone = normalize_phone(cells[phone_col]) if phone_col is not None else None
        if phone_col is not None and phone is None:
            errors.append('Số điện thoại không hợp lệ' if cells[phone_col] is not None else 'Thiếu số điện thoại')
        elif phone in seen_phones:
            errors.append(f'Trùng số điện thoại với dòng {seen_phones[phone]}')
        elif phone:
            seen_phones[phone] = row['row_no']
        for v in variables:
            if v['source'] != 'customer':
                continue
            col = mapping.get(v['name'])
            value, error = coerce(v['data_type'], cells[col] if col is not None else None)
            if error:
                errors.append(f'{v["name"]}: {error}')
            elif value is None and col is not None:
                errors.append(f'Thiếu {v["label"] or v["name"]}')
            values[v['name']] = value
            shown[v['name']] = display(v['data_type'], value)
        results.append(
            {
                'row_no': row['row_no'],
                'phone': phone,
                'raw_phone': None if phone_col is None else cells[phone_col],
                'customer': _customer_label(variables, values),
                'errors': errors,
                'valid': not errors and not mapping_errors and not fixed_errors,
                'content': render(template['content'], shown),
                '_params': {v['name']: shown.get(v['name']) or '' for v in variables},
            }
        )
    valid = sum(1 for r in results if r['valid'])
    return {
        'draft': draft,
        'template': template,
        'variables': variables,
        'mapping': mapping,
        'fixed_values': fixed_values,
        'fixed_input': fixed_input,
        'fixed_display': fixed_display,
        'fixed_errors': fixed_errors,
        'mapping_errors': mapping_errors,
        'warnings': warnings,
        'rows': results,
        'summary': {'total': len(results), 'valid': valid, 'invalid': len(results) - valid},
    }


def _template_public(template: dict[str, Any]) -> dict[str, Any]:
    keys = ('id', 'name', 'zns_code', 'owner', 'content')
    return {**{k: template[k] for k in keys}, 'variables': [v for v in template['variables'] if v['is_active']]}


def evaluate(batch_id: int, template_id: int, mapping: Any, fixed: Any, actor: Any) -> dict[str, Any]:
    with connection.cursor() as cursor:
        result = _evaluate(cursor, batch_id, template_id, mapping, fixed, actor)
    return {
        'template': _template_public(result['template']),
        'columns': result['draft']['columns'],
        'mapping': result['mapping'],
        'fixed': {name: {'input': result['fixed_input'][name], 'display': result['fixed_display'][name]} for name in result['fixed_input']},
        'fixed_errors': result['fixed_errors'],
        'mapping_errors': result['mapping_errors'],
        'warnings': result['warnings'],
        'rows': [{k: v for k, v in r.items() if not k.startswith('_')} for r in result['rows']],
        'summary': result['summary'],
    }


def _insert_many(cursor: Any, table: str, columns: list[str], values: list[list[Any]]) -> None:
    if not values:
        return
    per_row = len(columns)
    batch = max(1, MAX_SQL_PARAMS // per_row)
    placeholder = '(' + ', '.join(['%s'] * per_row) + ')'
    cols = ', '.join(columns)
    for i in range(0, len(values), batch):
        chunk = values[i : i + batch]
        cursor.execute(f'INSERT INTO {table} ({cols}) VALUES ' + ', '.join([placeholder] * len(chunk)), [x for r in chunk for x in r])


@retry_on_deadlock
def confirm(batch_id: int, template_id: int, mapping: Any, fixed: Any, actor: Any) -> dict[str, Any]:
    """Chốt danh sách + tham số từng khách, chuyển lô sang "Đang gửi" và gửi ở luồng nền sau khi commit."""
    mode = provider.send_mode()
    with transaction.atomic(), connection.cursor() as cursor:
        # Giữ khóa mẫu đến khi có lô: không để mẫu bị xóa giữa chừng.
        cursor.execute('SELECT Id FROM dbo.ZnsTemplates WITH (UPDLOCK, ROWLOCK) WHERE Id = %s', [template_id])
        cursor.fetchall()
        result = _evaluate(cursor, batch_id, template_id, mapping, fixed, actor)
        if result['mapping_errors'] or result['fixed_errors']:
            raise MessagingError('Còn lỗi ở cấu hình cột hoặc biến cố định, vui lòng kiểm tra lại.')
        if not result['summary']['valid']:
            raise MessagingError('Không có khách hàng hợp lệ để gửi.')
        provider.check_account(result['template']['owner'])
        cursor.execute("UPDATE dbo.ZnsSendBatches SET Status = 'sending' WHERE Id = %s AND Status = 'draft'", [batch_id])
        if cursor.rowcount != 1:
            raise MessagingError('Danh sách này đã được xác nhận gửi trước đó.')
        template = result['template']
        recipients = [
            [batch_id, r['row_no'], r['phone'] or (str(r['raw_phone'])[:20] if r['raw_phone'] is not None else None), (r['customer'] or '')[:200] or None,
             r['content'] if r['valid'] else None, 'pending' if r['valid'] else 'invalid', '; '.join(r['errors'])[:1000] or None,
             json.dumps(r['_params'], ensure_ascii=False) if r['valid'] else None]
            for r in result['rows']
        ]
        _insert_many(
            cursor, 'dbo.ZnsSendRecipients', ['BatchId', 'RowNo', 'Phone', 'CustomerName', 'Content', 'Status', 'ErrorMessage', 'Params'], recipients
        )
        fixed_json = {v['name']: to_json(v['data_type'], result['fixed_values'][v['name']]) for v in result['variables'] if v['source'] == 'fixed'}
        mapping_json = {k: (result['draft']['columns'][i] if i is not None else None) for k, i in result['mapping'].items()}
        summary = result['summary']
        cursor.execute(
            """
            UPDATE dbo.ZnsSendBatches SET TemplateId = %s, TemplateName = %s, Owner = %s, ColumnMapping = %s, FixedValues = %s, RawData = NULL,
                   TotalRows = %s, ValidRows = %s, InvalidRows = %s, ConfirmedBy = %s, ConfirmedAt = SYSUTCDATETIME(),
                   SendMode = %s, SentBy = %s, SendStartedAt = SYSUTCDATETIME(), DepartmentId = %s
            WHERE Id = %s
            """,
            [template['id'], template['name'], template['owner'], json.dumps(mapping_json, ensure_ascii=False), json.dumps(fixed_json, ensure_ascii=False),
             summary['total'], summary['valid'], summary['invalid'], actor.username, mode, actor.username, template['department_id'], batch_id],
        )
        audit.log('zns.confirm', actor.username, 'batch', batch_id, f'{template["owner"]} · mẫu {template["zns_code"]} · {summary["valid"]} khách · {mode}')
        audit.assign_batch_department(batch_id, template['department_id'])
        transaction.on_commit(lambda: _start_thread(batch_id))
    return {'batch_id': batch_id, 'send_mode': mode, **summary}


def _visibility(actor: Any) -> tuple[str, list[Any]]:
    if not actor.owners:
        return '1 = 0', []
    clause, args = f"b.Owner IN ({', '.join(['%s'] * len(actor.owners))})", [*actor.owners]
    if not actor.all_departments:
        # Lô cũ chưa xác định được phòng ban: người tạo vẫn thấy lô của mình.
        own_old = '(b.DepartmentId IS NULL AND (b.CreatedBy = %s OR b.ConfirmedBy = %s))'
        args += [*actor.departments, actor.username, actor.username]
        mine = f"b.DepartmentId IN ({', '.join(['%s'] * len(actor.departments))}) OR " if actor.departments else ''
        clause += f' AND ({mine}{own_old})'
    if actor.view_all:
        return clause, args
    return f'{clause} AND (b.CreatedBy = %s OR b.ConfirmedBy = %s)', [*args, actor.username, actor.username]


def list_batches(draw: int, start: int, length: int, actor: Any) -> dict[str, Any]:
    visible, args = _visibility(actor)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM dbo.ZnsSendBatches b WHERE b.Status <> 'draft' AND {visible}", args)
        total = cursor.fetchone()[0]
        cursor.execute(
            f"""
            SELECT b.Id AS id, b.FileName AS file_name, b.Owner AS owner, b.Status AS status,
                   b.TotalRows AS total_rows, b.ValidRows AS valid_rows, b.InvalidRows AS invalid_rows,
                   b.CreatedBy AS created_by, b.ConfirmedAt AS confirmed_at, COALESCE(b.TemplateName, t.Name) AS template_name, t.ZnsCode AS zns_code,
                   b.SendMode AS send_mode, b.SentRows AS sent_rows, b.FailedRows AS failed_rows, b.UnknownRows AS unknown_rows, b.SkippedRows AS skipped_rows,
                   b.ParentBatchId AS parent_batch_id, b.ConfirmedBy AS confirmed_by, b.SendDurationSeconds AS duration_seconds, b.SendDurationMs AS duration_ms, b.DepartmentId AS department_id
            FROM dbo.ZnsSendBatches b LEFT JOIN dbo.ZnsTemplates t ON t.Id = b.TemplateId
            WHERE b.Status <> 'draft' AND {visible}
            ORDER BY b.Id DESC
            OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
            """,
            [*args, start, length],
        )
        data = rows(cursor)
    for r in data:
        r['confirmed_at'] = iso_utc(r['confirmed_at'])
        r['status_label'] = _status_label(r['status'], r['send_mode'])
        r['duration_label'] = _duration_label(r.pop('duration_ms'), r.pop('duration_seconds'))
        r['can_cancel'] = r['status'] in CANCELLABLE and actor.can_cancel(r['owner'], r['created_by'], r.pop('confirmed_by'), r.pop('department_id'))
    return {'draw': draw, 'recordsTotal': total, 'recordsFiltered': total, 'data': data}


def _batch(cursor: Any, batch_id: int) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT b.Id, b.FileName, b.Owner, b.Status, b.TotalRows, b.ValidRows, b.InvalidRows, b.FixedValues, b.ColumnMapping,
               b.CreatedBy, b.ConfirmedAt, COALESCE(b.TemplateName, t.Name), t.ZnsCode, b.SendMode, b.SendFinishedAt, b.SentRows, b.FailedRows,
               b.UnknownRows, b.ParentBatchId, b.ConfirmedBy, b.SkippedRows, b.SendPauseNote, b.DepartmentId
        FROM dbo.ZnsSendBatches b LEFT JOIN dbo.ZnsTemplates t ON t.Id = b.TemplateId
        WHERE b.Id = %s AND b.Status <> 'draft'
        """,
        [batch_id],
    )
    row = cursor.fetchone()
    if not row:
        raise MessagingError('Không tìm thấy lô gửi.')
    keys = ('id', 'file_name', 'owner', 'status', 'total_rows', 'valid_rows', 'invalid_rows', 'fixed', 'mapping', 'created_by', 'confirmed_at', 'template_name', 'zns_code', 'send_mode', 'finished_at', 'sent_rows', 'failed_rows',
            'unknown_rows', 'parent_batch_id', 'confirmed_by', 'skipped_rows', 'pause_note', 'department_id')
    batch = dict(zip(keys, row))
    batch['fixed'] = json.loads(batch['fixed'] or '{}')
    batch['mapping'] = json.loads(batch['mapping'] or '{}')
    batch['confirmed_at'] = iso_utc(batch['confirmed_at'])
    batch['finished_at'] = iso_utc(batch['finished_at'])
    batch['status_label'] = _status_label(batch['status'], batch['send_mode'])
    return batch


def _visible_batch(cursor: Any, batch_id: int, actor: Any) -> dict[str, Any]:
    batch = _batch(cursor, batch_id)
    if not actor.can_see(batch['owner'], batch['created_by'], batch['confirmed_by'], batch['department_id']):
        raise MessagingError('Không tìm thấy lô gửi.')
    return batch


def _recipients(cursor: Any, batch_id: int, status: str | None = None, start: int | None = None, length: int | None = None) -> list[dict[str, Any]]:
    paging = f'OFFSET {int(start)} ROWS FETCH NEXT {int(length)} ROWS ONLY' if length else ''
    where = f'AND {RECIPIENT_FILTERS[status]}' if status in RECIPIENT_FILTERS else ''
    cursor.execute(
        f"""
        SELECT Id AS id, RowNo AS row_no, Phone AS phone, CustomerName AS customer, Content AS content, Status AS status,
               ErrorMessage AS error, ErrorKind AS error_kind, AttemptCount AS attempt_count, RetryCount AS retry_count,
               RetriedInBatchId AS retried_in, SentAt AS sent_at, SkipReason AS skip_reason, SkippedBy AS skipped_by
        FROM dbo.ZnsSendRecipients WITH (INDEX({_BATCH_ROW_INDEX})) WHERE BatchId = %s {where} ORDER BY RowNo {paging}
        """,
        [batch_id],
    )
    data = rows(cursor)
    for r in data:
        r['status_label'] = STATUS_LABELS.get(r['status'], r['status'])
        r['error_kind_label'] = ERROR_KIND_LABELS.get(r['error_kind'])
        r['sent_at'] = iso_utc(r['sent_at'])
    return data


def _retry_options(cursor: Any, batch_id: int, batch_status: str) -> dict[str, int]:
    eligible = f'RetriedInBatchId IS NULL AND RetryCount < {ZNS_MAX_MANUAL_RETRIES}'
    cursor.execute(
        f"""
        SELECT COUNT(CASE WHEN {eligible} AND Status = 'failed' AND ErrorKind = 'temporary' THEN 1 END),
               COUNT(CASE WHEN {eligible} AND Status = 'unknown' THEN 1 END),
               COUNT(CASE WHEN RetriedInBatchId IS NULL AND ({_NEW_BATCH_CLAUSE}) THEN 1 END)
        FROM dbo.ZnsSendRecipients WHERE BatchId = %s
        """,
        [batch_id],
    )
    temporary, unknown, new_batch = cursor.fetchone()
    finished = batch_status in ('partial', 'failed')
    return {
        'temporary': temporary if finished else 0,
        'unknown': unknown if finished else 0,
        'new_batch': new_batch if finished or batch_status == 'paused' else 0,
    }


def list_recipients(batch_id: int, actor: Any, draw: int, start: int, length: int, status: str | None = None) -> dict[str, Any]:
    status = status if status in RECIPIENT_FILTERS else None
    with connection.cursor() as cursor:
        _visible_batch(cursor, batch_id, actor)
        cursor.execute('SELECT COUNT(*) FROM dbo.ZnsSendRecipients WHERE BatchId = %s', [batch_id])
        total = cursor.fetchone()[0]
        filtered = total
        if status:
            cursor.execute(f'SELECT COUNT(*) FROM dbo.ZnsSendRecipients WHERE BatchId = %s AND {RECIPIENT_FILTERS[status]}', [batch_id])
            filtered = cursor.fetchone()[0]
        data = _recipients(cursor, batch_id, status, start, length)
    return {'draw': draw, 'recordsTotal': total, 'recordsFiltered': filtered, 'data': data}


def batch_detail(batch_id: int, actor: Any) -> dict[str, Any]:
    with connection.cursor() as cursor:
        batch = _visible_batch(cursor, batch_id, actor)
        cursor.execute(
            """
            SELECT Status, Kind, Message, Total FROM (
                SELECT Status, Kind, Message, COUNT(*) AS Total,
                       ROW_NUMBER() OVER (PARTITION BY Status ORDER BY COUNT(*) DESC) AS Position
                FROM (
                    SELECT Status,
                           CASE WHEN Status = 'skipped' THEN NULL ELSE ErrorKind END AS Kind,
                           CASE WHEN Status = 'skipped' THEN SkipReason ELSE ErrorMessage END AS Message
                    FROM dbo.ZnsSendRecipients
                    WHERE BatchId = %s AND Status IN ('failed', 'unknown', 'invalid', 'skipped')
                ) errors
                GROUP BY Status, Kind, Message
            ) grouped
            WHERE Position <= 20
            ORDER BY Total DESC
            """,
            [batch_id],
        )
        batch['error_summary'] = [{'status': s, 'kind_label': ERROR_KIND_LABELS.get(k), 'message': m, 'count': c} for s, k, m, c in cursor.fetchall()]
        batch['retry_options'] = _retry_options(cursor, batch_id, batch['status'])
        cursor.execute(
            f"""
            SELECT COUNT(CASE WHEN {_SKIP_CLAUSE} THEN 1 END),
                   COUNT(CASE WHEN {RECIPIENT_FILTERS['waiting']} THEN 1 END),
                   COUNT(CASE WHEN {RECIPIENT_FILTERS['cancelled']} THEN 1 END)
            FROM dbo.ZnsSendRecipients WHERE BatchId = %s
            """,
            [batch_id],
        )
        skip_count, batch['waiting_rows'], batch['cancelled_rows'] = cursor.fetchone()
    people = (batch['owner'], batch['created_by'], batch['confirmed_by'], batch['department_id'])
    batch['can_retry'] = actor.can_retry(*people)
    batch['can_skip'] = batch['status'] in SKIPPABLE and actor.can_retry(*people)
    batch['skip_count'] = skip_count
    return batch


def recipient_attempts(batch_id: int, recipient_id: int, actor: Any) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        _visible_batch(cursor, batch_id, actor)
        cursor.execute(
            """
            SELECT AttemptNo AS attempt_no, TriggerType AS trigger_type, TriggeredBy AS triggered_by, Result AS result, HttpStatus AS http_status,
                   DurationMs AS duration_ms, ErrorMessage AS error, ApiResponse AS response, CreatedAt AS created_at
            FROM dbo.ZnsSendAttempts WHERE BatchId = %s AND RecipientId = %s ORDER BY AttemptNo
            """,
            [batch_id, recipient_id],
        )
        data = rows(cursor)
    for r in data:
        r['result_label'] = ATTEMPT_RESULT_LABELS.get(r['result'], r['result'])
        r['created_at'] = iso_utc(r['created_at'])
    return data


def batch_export_rows(batch_id: int, status: str | None, actor: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with connection.cursor() as cursor:
        return _visible_batch(cursor, batch_id, actor), _recipients(cursor, batch_id, status)


@retry_on_deadlock
def cancel_batch(batch_id: int, actor: Any) -> None:
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute('SELECT Status, CreatedBy, ConfirmedBy, Owner, DepartmentId FROM dbo.ZnsSendBatches WITH (UPDLOCK, ROWLOCK) WHERE Id = %s', [batch_id])
        row = cursor.fetchone()
        if not row or not actor.can_see(row[3], row[1], row[2], row[4]) and not actor.can_cancel(row[3], row[1], row[2], row[4]):
            raise MessagingError('Không tìm thấy lô gửi.')
        if row[0] not in CANCELLABLE:
            raise MessagingError('Chỉ hủy được lô đang "Chờ gửi", "Đang gửi" hoặc "Tạm dừng".')
        if not actor.can_cancel(row[3], row[1], row[2], row[4]):
            raise MessagingError('Chỉ người tạo lô hoặc người có quyền hủy mới hủy được lô này.')
        cursor.execute(
            """
            UPDATE dbo.ZnsSendBatches SET Status = 'cancelled', CancelledBy = %s, CancelledAt = SYSUTCDATETIME()
            WHERE Id = %s AND Status IN ('pending', 'sending', 'paused')
            """,
            [actor.username, batch_id],
        )
        cursor.execute("UPDATE dbo.ZnsSendRecipients SET Status = 'cancelled' WHERE BatchId = %s AND Status = 'pending'", [batch_id])
        audit.log('zns.cancel', actor.username, 'batch', batch_id, f'Hủy {cursor.rowcount} khách chưa gửi · trạng thái trước đó: {row[0]}')


def _start_thread(batch_id: int, actor: str | None = None, resumed: bool = False) -> None:
    threading.Thread(target=_run_in_thread, args=(batch_id, actor, resumed), name=f'zns-send-{batch_id}', daemon=True).start()


@retry_on_deadlock
def _batch_status(batch_id: int) -> str | None:
    with connection.cursor() as cursor:
        cursor.execute('SELECT Status FROM dbo.ZnsSendBatches WHERE Id = %s', [batch_id])
        row = cursor.fetchone()
    return row[0] if row else None


def _run_in_thread(batch_id: int, actor: str | None = None, resumed: bool = False) -> None:
    try:
        run_send(batch_id, actor, resumed)
    except MessagingError as exc:
        logger.info('ZNS: lô %s không chạy: %s', batch_id, exc)
    except Exception:
        logger.exception('ZNS: lô %s dừng giữa chừng, giữ trạng thái "Đang gửi", sẽ tự chạy tiếp sau %s giây', batch_id, ZNS_RESUME_AFTER_SECONDS)
    finally:
        connection.close()


@retry_on_deadlock
def _pause_stopped_batch(batch_id: int, note: str) -> bool:
    """Tiến trình gửi đã dừng mà không nên tự gửi tiếp: chuyển "Tạm dừng" để người dùng quyết định."""
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE dbo.ZnsSendBatches SET Status = 'paused', SendPauseNote = %s
            WHERE Id = %s AND Status = 'sending'
                  AND COALESCE(SendHeartbeatAt, SendStartedAt) < DATEADD(SECOND, -{ZNS_RESUME_AFTER_SECONDS}, SYSUTCDATETIME())
            """,
            [note, batch_id],
        )
        if cursor.rowcount != 1:
            return False
        _recover_interrupted(batch_id)
        _refresh_counts(cursor, batch_id)
        audit.log('zns.stale_pause', 'system', 'batch', batch_id, note)
    return True


def resume_stale_batches() -> None:
    """Xử lý lô "Đang gửi" mà tiến trình gửi đã dừng: dừng chưa lâu thì tự gửi tiếp, quá lâu thì tạm dừng. Chỉ nhận lô cùng chế độ gửi với server này."""
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT Id, SendResumeCount, CASE WHEN COALESCE(SendHeartbeatAt, SendStartedAt) < DATEADD(SECOND, -{ZNS_RESUME_MAX_SECONDS}, SYSUTCDATETIME()) THEN 1 ELSE 0 END
            FROM dbo.ZnsSendBatches
            WHERE Status = 'sending' AND SendMode = %s
                  AND COALESCE(SendHeartbeatAt, SendStartedAt) < DATEADD(SECOND, -{ZNS_RESUME_AFTER_SECONDS}, SYSUTCDATETIME())
            """,
            [provider.send_mode()],
        )
        stale = cursor.fetchall()
    for batch_id, resume_count, too_old in stale:
        if too_old:
            note = f'Việc gửi đã dừng quá {ZNS_RESUME_MAX_SECONDS // 3600} giờ nên hệ thống không tự gửi tiếp. Tạo lô mới để gửi các khách chưa gửi, hoặc hủy lô.'
        elif resume_count >= ZNS_MAX_AUTO_RESUMES:
            note = f'Việc gửi đã bị ngắt và tự chạy lại {resume_count} lần vẫn không xong nên hệ thống dừng lại. Kiểm tra server rồi tạo lô mới để gửi các khách chưa gửi, hoặc hủy lô.'
        else:
            _start_thread(batch_id, resumed=True)
            continue
        if _pause_stopped_batch(batch_id, note):
            logger.warning('ZNS: tạm dừng lô %s: %s', batch_id, note)


def _watch() -> None:
    while True:
        time.sleep(ZNS_WATCH_INTERVAL_SECONDS + random.uniform(0, 10))
        try:
            resume_stale_batches()
        except Exception:
            logger.exception('ZNS: không kiểm tra được lô đang gửi')
        finally:
            connection.close()


def start_watcher() -> None:
    threading.Thread(target=_watch, name='zns-watch', daemon=True).start()


def _refresh_counts(cursor: Any, batch_id: int) -> None:
    cursor.execute(
        """
        UPDATE b SET
            SentRows = (SELECT COUNT(*) FROM dbo.ZnsSendRecipients r WHERE r.BatchId = b.Id AND r.Status IN ('sent', 'simulated')),
            FailedRows = (SELECT COUNT(*) FROM dbo.ZnsSendRecipients r WHERE r.BatchId = b.Id AND r.Status = 'failed'),
            UnknownRows = (SELECT COUNT(*) FROM dbo.ZnsSendRecipients r WHERE r.BatchId = b.Id AND r.Status = 'unknown'),
            SkippedRows = (SELECT COUNT(*) FROM dbo.ZnsSendRecipients r WHERE r.BatchId = b.Id AND r.Status = 'skipped')
        FROM dbo.ZnsSendBatches b WHERE b.Id = %s
        """,
        [batch_id],
    )


def _final_status(cursor: Any, batch_id: int) -> str:
    """Trạng thái cuối theo kết quả: tất cả thành công / một phần / không khách nào thành công."""
    _refresh_counts(cursor, batch_id)
    cursor.execute('SELECT SentRows, FailedRows, UnknownRows FROM dbo.ZnsSendBatches WHERE Id = %s', [batch_id])
    sent, failed, unknown = cursor.fetchone()
    return 'failed' if not sent else ('partial' if failed or unknown else 'done')


def _finish_batch(cursor: Any, batch_id: int, from_status: str = 'sending') -> str:
    status = _final_status(cursor, batch_id)
    cursor.execute(
        'UPDATE dbo.ZnsSendBatches SET Status = %s, SendFinishedAt = SYSUTCDATETIME() WHERE Id = %s AND Status = %s', [status, batch_id, from_status]
    )
    return status


@retry_on_deadlock
def _recover_interrupted(batch_id: int) -> None:
    """Khách đang được gửi lúc server dừng: không biết tin đã đi chưa, không tự gửi lại."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE dbo.ZnsSendRecipients SET Status = 'unknown', ErrorKind = 'unknown',
                   ErrorMessage = N'Server dừng khi đang gửi khách này. Tin có thể đã được gửi.'
            WHERE BatchId = %s AND Status = 'sending'
            """,
            [batch_id],
        )


@retry_on_deadlock
def _log_attempt(batch_id: int, recipient_id: int, attempt_no: int, trigger: str, actor: str | None, result: provider.SendResult) -> None:
    outcome = 'simulated' if result.simulated else ('sent' if result.ok else result.kind)
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO dbo.ZnsSendAttempts (BatchId, RecipientId, AttemptNo, TriggerType, TriggeredBy, Result, HttpStatus, DurationMs, ErrorMessage, ApiResponse)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [batch_id, recipient_id, attempt_no, trigger, actor, outcome, result.http_status, result.duration_ms, result.error, result.response],
        )
        cursor.execute('UPDATE dbo.ZnsSendRecipients SET AttemptCount = %s WHERE Id = %s', [attempt_no, recipient_id])


def _send_one(batch_id: int, owner: str, template_code: str, row: tuple, actor: str | None) -> provider.SendResult:
    """Gửi một khách: lỗi tạm thời tự thử lại theo ZNS_RETRY_DELAYS, mỗi lần gọi ghi vào ZnsSendAttempts."""
    recipient_id, phone, params, attempt_count, retry_count = row
    manual = retry_count > 0
    attempt_no = attempt_count
    for index in range(len(ZNS_RETRY_DELAYS) + 1):
        attempt_no += 1
        if params is None:
            result = provider.SendResult(ok=False, kind=provider.KIND_BUSINESS, error='Thiếu tham số (lô xác nhận trước khi có chức năng gửi), hãy tạo lại lô.')
        else:
            result = provider.send(owner, phone, template_code, json.loads(params))
        trigger = 'manual' if manual and index == 0 else 'auto'
        _log_attempt(batch_id, recipient_id, attempt_no, trigger, actor if trigger == 'manual' else None, result)
        logger.info(
            'ZNS lô=%s khách=%s sđt=%s lần=%s kết_quả=%s http=%s ms=%s',
            batch_id, recipient_id, provider.mask_phone(phone), attempt_no,
            'simulated' if result.simulated else ('sent' if result.ok else result.kind), result.http_status, result.duration_ms,
        )
        if result.ok or result.kind != provider.KIND_TEMPORARY or index == len(ZNS_RETRY_DELAYS) or _batch_status(batch_id) != 'sending':
            return result
        time.sleep(ZNS_RETRY_DELAYS[index])
    return result


@retry_on_deadlock
def _send_info(batch_id: int) -> tuple | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT b.Status, b.Owner, b.SendMode, t.ZnsCode, COALESCE(b.SendDurationMs, CAST(b.SendDurationSeconds AS BIGINT) * 1000)
            FROM dbo.ZnsSendBatches b JOIN dbo.ZnsTemplates t ON t.Id = b.TemplateId WHERE b.Id = %s
            """,
            [batch_id],
        )
        return cursor.fetchone()


@retry_on_deadlock
def _claim_run(batch_id: int, run_id: str, resumed: bool) -> bool:
    """Mỗi lô chỉ một tiến trình gửi: chỉ nhận được lô chưa ai giữ, hoặc người giữ đã im quá lâu."""
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE dbo.ZnsSendBatches SET SendRunId = %s, SendHeartbeatAt = SYSUTCDATETIME(), SendResumeCount = SendResumeCount + %s
            WHERE Id = %s AND Status = 'sending'
                  AND (SendRunId IS NULL OR SendHeartbeatAt < DATEADD(SECOND, -{ZNS_RESUME_AFTER_SECONDS}, SYSUTCDATETIME()))
            """,
            [run_id, int(resumed), batch_id],
        )
        return cursor.rowcount == 1


@retry_on_deadlock
def _beat(batch_id: int, run_id: str, duration_ms: int) -> bool:
    """Báo tiến trình còn hoạt động và lưu thời lượng. False: lô đã bị tiến trình khác nhận lại."""
    with connection.cursor() as cursor:
        cursor.execute(
            'UPDATE dbo.ZnsSendBatches SET SendDurationMs = %s, SendDurationSeconds = %s, SendHeartbeatAt = SYSUTCDATETIME() WHERE Id = %s AND SendRunId = %s',
            [duration_ms, duration_ms // 1000, batch_id, run_id],
        )
        return cursor.rowcount == 1


@retry_on_deadlock
def _pending_chunk(batch_id: int) -> list[tuple]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT TOP {SEND_CHUNK} Id, Phone, Params, AttemptCount, RetryCount
            FROM dbo.ZnsSendRecipients WITH (INDEX({_BATCH_ROW_INDEX})) WHERE BatchId = %s AND Status = 'pending' ORDER BY RowNo
            """,
            [batch_id],
        )
        return cursor.fetchall()


@retry_on_deadlock
def _claim_recipient(recipient_id: int) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("UPDATE dbo.ZnsSendRecipients SET Status = 'sending' WHERE Id = %s AND Status = 'pending'", [recipient_id])
        return cursor.rowcount == 1


@retry_on_deadlock
def _save_result(batch_id: int, recipient_id: int, status: str, result: provider.SendResult) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE dbo.ZnsSendRecipients SET Status = %s, ErrorKind = %s, ErrorMessage = %s, ApiResponse = %s, ZaloMsgId = %s,
                   SentAt = CASE WHEN %s = 'sent' THEN SYSUTCDATETIME() ELSE SentAt END
            WHERE Id = %s AND Status = 'sending'
            """,
            [status, result.kind, result.error, result.response, result.msg_id, status, recipient_id],
        )
        _refresh_counts(cursor, batch_id)


@retry_on_deadlock
def _pause_batch(batch_id: int, detail: str, note: str | None = None) -> None:
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("UPDATE dbo.ZnsSendBatches SET Status = 'paused', SendPauseNote = %s WHERE Id = %s AND Status = 'sending'", [note, batch_id])
        if cursor.rowcount:
            audit.log('zns.pause', 'system', 'batch', batch_id, detail)


@retry_on_deadlock
def _finish_run(batch_id: int) -> str:
    with transaction.atomic(), connection.cursor() as cursor:
        final = _finish_batch(cursor, batch_id)
        cursor.execute('SELECT SentRows, FailedRows, UnknownRows FROM dbo.ZnsSendBatches WHERE Id = %s', [batch_id])
        sent, failed, unknown = cursor.fetchone()
        audit.log('zns.finish', 'system', 'batch', batch_id, f'{BATCH_STATUS_LABELS.get(final, final)} · thành công {sent} · lỗi {failed} · chưa rõ {unknown}')
    return final


def run_send(batch_id: int, actor: str | None = None, resumed: bool = False) -> dict[str, int]:
    """Gửi lần lượt khách "Chờ gửi" của lô đang "Đang gửi". Chạy lại được nếu bị dừng giữa chừng."""
    row = _send_info(batch_id)
    if not row or row[0] != 'sending':
        raise MessagingError('Lô không ở trạng thái "Đang gửi".')
    owner, mode, template_code = row[1], row[2], row[3]
    if mode != provider.send_mode():
        raise MessagingError(f'Lô bắt đầu ở chế độ {mode}, server đang ở chế độ {provider.send_mode()}: không tự đổi chế độ giữa chừng.')
    run_id = str(uuid.uuid4())
    if not _claim_run(batch_id, run_id, resumed):
        raise MessagingError(f'Lô đang được tiến trình khác gửi, hoặc vừa dừng chưa quá {ZNS_RESUME_AFTER_SECONDS} giây.')
    _recover_interrupted(batch_id)
    if resumed:
        audit.log('zns.resume', 'system', 'batch', batch_id, 'Tiến trình gửi đã dừng, tự chạy tiếp các khách còn lại')
        logger.warning('ZNS: tự chạy tiếp lô %s', batch_id)
    started, earlier_ms = time.monotonic(), row[4] or 0

    def beat() -> bool:
        return _beat(batch_id, run_id, earlier_ms + int((time.monotonic() - started) * 1000))

    counts = {'sent': 0, 'failed': 0, 'unknown': 0, 'simulated': 0}
    last_config_error, config_streak, error_streak = None, 0, 0
    while True:
        chunk = _pending_chunk(batch_id)
        if not chunk:
            break
        for recipient in chunk:
            if _batch_status(batch_id) != 'sending':
                beat()
                logger.info('ZNS: lô %s đã bị hủy giữa chừng %s', batch_id, counts)
                return counts
            recipient_id = recipient[0]
            if not _claim_recipient(recipient_id):
                continue
            result = _send_one(batch_id, owner, template_code, recipient, actor)
            status = 'simulated' if result.simulated else ('sent' if result.ok else ('unknown' if result.kind == provider.KIND_UNKNOWN else 'failed'))
            counts[status] += 1
            _save_result(batch_id, recipient_id, status, result)
            if not beat():
                logger.warning('ZNS: lô %s đã được tiến trình khác nhận lại, dừng tiến trình này %s', batch_id, counts)
                return counts
            if result.kind == provider.KIND_CONFIG:
                config_streak = config_streak + 1 if result.error == last_config_error else 1
                last_config_error = result.error
                if config_streak >= ZNS_PAUSE_AFTER:
                    _pause_batch(batch_id, f'{config_streak} lỗi cấu hình liên tiếp: {result.error}')
                    logger.warning('ZNS: tạm dừng lô %s sau %s lỗi cấu hình liên tiếp: %s', batch_id, config_streak, result.error)
                    return counts
            else:
                last_config_error, config_streak = None, 0
            error_streak = 0 if result.ok else error_streak + 1
            if error_streak >= ZNS_PAUSE_AFTER_ERRORS:
                note = f'{error_streak} khách liên tiếp đều lỗi nên hệ thống dừng lại. Lỗi gần nhất: {result.error or "không rõ"}'[:250] + ' Kiểm tra rồi tạo lô mới hoặc hủy lô.'
                _pause_batch(batch_id, note, note)
                logger.warning('ZNS: tạm dừng lô %s: %s', batch_id, note)
                return counts
            if not result.simulated and ZNS_SEND_DELAY_MS:
                time.sleep(ZNS_SEND_DELAY_MS / 1000)
    final = _finish_run(batch_id)
    beat()
    logger.info('ZNS: xong lô %s (%s) trạng_thái=%s %s', batch_id, mode, final, counts)
    return counts


@retry_on_deadlock
def skip_recipients(batch_id: int, recipient_id: Any, reason: Any, actor: Any) -> dict[str, Any]:
    """Bỏ qua khách lỗi: một khách theo recipient_id, hoặc mọi khách lỗi còn lại của lô khi không truyền. Không hoàn tác."""
    reason = str(reason or '').strip()[:500]
    if not reason:
        raise MessagingError('Vui lòng nhập lý do bỏ qua.')
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute('SELECT Status, Owner, CreatedBy, ConfirmedBy, DepartmentId FROM dbo.ZnsSendBatches WITH (UPDLOCK, ROWLOCK) WHERE Id = %s', [batch_id])
        row = cursor.fetchone()
        if not row or not actor.can_see(row[1], row[2], row[3], row[4]):
            raise MessagingError('Không tìm thấy lô gửi.')
        status = row[0]
        if status not in SKIPPABLE:
            raise MessagingError('Chỉ bỏ qua được khách của lô "Gửi một phần", "Thất bại" hoặc "Tạm dừng".')
        if not actor.can_retry(row[1], row[2], row[3], row[4]):
            raise MessagingError('Chỉ người tạo lô hoặc người có quyền gửi lại mới bỏ qua được khách lỗi.')
        where, args = _SKIP_CLAUSE, [batch_id]
        if recipient_id is not None:
            try:
                args.append(int(recipient_id))
            except (TypeError, ValueError) as exc:
                raise MessagingError('Khách không hợp lệ.') from exc
            where += ' AND Id = %s'
        cursor.execute(
            f"""
            UPDATE dbo.ZnsSendRecipients SET Status = 'skipped', SkipReason = %s, SkippedBy = %s, SkippedAt = SYSUTCDATETIME()
            WHERE BatchId = %s AND {where}
            """,
            [reason, actor.username, *args],
        )
        skipped = cursor.rowcount
        if not skipped:
            raise MessagingError('Không còn khách lỗi nào để bỏ qua.')
        if status == 'paused':
            _refresh_counts(cursor, batch_id)
        else:
            new_status = _final_status(cursor, batch_id)
            cursor.execute('UPDATE dbo.ZnsSendBatches SET Status = %s WHERE Id = %s', [new_status, batch_id])
        audit.log('zns.skip', actor.username, 'batch', batch_id, f'{skipped} khách · {reason}')
    return {'batch_id': batch_id, 'skipped': skipped}


@retry_on_deadlock
def retry_same_batch(batch_id: int, kinds: Any, actor: Any) -> dict[str, Any]:
    """Gửi lại ngay trên lô cũ: lỗi tạm thời và / hoặc chưa rõ kết quả. Nội dung không đổi."""
    clauses = {'temporary': "(Status = 'failed' AND ErrorKind = 'temporary')", 'unknown': "Status = 'unknown'"}
    chosen = [clauses[k] for k in clauses if isinstance(kinds, list) and k in kinds]
    if not chosen:
        raise MessagingError('Chưa chọn loại lỗi cần gửi lại.')
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute('SELECT Status, CreatedBy, ConfirmedBy, SendMode, Owner, DepartmentId FROM dbo.ZnsSendBatches WITH (UPDLOCK, ROWLOCK) WHERE Id = %s', [batch_id])
        row = cursor.fetchone()
        if not row or row[0] not in ('partial', 'failed'):
            raise MessagingError('Chỉ gửi lại được lô "Gửi một phần" hoặc "Thất bại".')
        if not actor.can_retry(row[4], row[1], row[2], row[5]):
            raise MessagingError('Chỉ người tạo lô hoặc người có quyền gửi lại mới gửi lại được.')
        if row[3] != provider.send_mode():
            raise MessagingError(f'Lô đã gửi ở chế độ {row[3]}, server đang ở chế độ {provider.send_mode()}.')
        provider.check_account(row[4])
        cursor.execute(
            f"""
            UPDATE dbo.ZnsSendRecipients SET Status = 'pending', ErrorKind = NULL, ErrorMessage = NULL, RetryCount = RetryCount + 1
            WHERE BatchId = %s AND RetriedInBatchId IS NULL AND RetryCount < {ZNS_MAX_MANUAL_RETRIES} AND ({' OR '.join(chosen)})
            """,
            [batch_id],
        )
        retried = cursor.rowcount
        if not retried:
            raise MessagingError(f'Không còn khách nào gửi lại được (tối đa {ZNS_MAX_MANUAL_RETRIES} lần mỗi khách).')
        cursor.execute("UPDATE dbo.ZnsSendBatches SET Status = 'sending', SendFinishedAt = NULL, SendRunId = NULL, SendHeartbeatAt = SYSUTCDATETIME(), SendResumeCount = 0 WHERE Id = %s", [batch_id])
        _refresh_counts(cursor, batch_id)
        audit.log('zns.retry', actor.username, 'batch', batch_id, f'{retried} khách · {", ".join(k for k in clauses if k in kinds)}')
        transaction.on_commit(lambda: _start_thread(batch_id, actor.username))
    return {'batch_id': batch_id, 'retried': retried}


def _link_retry(cursor: Any, parent_id: int, child_id: int) -> None:
    """Đánh dấu khách ở lô gốc đã chuyển sang lô gửi lại."""
    cursor.execute('SELECT Status FROM dbo.ZnsSendBatches WHERE Id = %s', [parent_id])
    parent_status = cursor.fetchone()[0]
    cursor.execute(
        f"""
        SELECT Id FROM dbo.ZnsSendRecipients
        WHERE BatchId = %s AND RetriedInBatchId IS NULL AND ({_NEW_BATCH_CLAUSE})
              AND RowNo IN (SELECT RowNo FROM dbo.ZnsSendRecipients WHERE BatchId = %s)
        """,
        [parent_id, child_id],
    )
    ids = [r[0] for r in cursor.fetchall()]
    for start in range(0, len(ids), MAX_SQL_PARAMS - 1):
        part = ids[start : start + MAX_SQL_PARAMS - 1]
        cursor.execute(
            f"""
            UPDATE dbo.ZnsSendRecipients SET RetriedInBatchId = %s,
                   Status = CASE WHEN Status = 'pending' THEN 'cancelled' ELSE Status END,
                   ErrorMessage = CASE WHEN Status = 'pending' THEN %s ELSE ErrorMessage END
            WHERE Id IN ({', '.join(['%s'] * len(part))})
            """,
            [child_id, f'Chuyển sang lô #{child_id}.', *part],
        )
    if parent_status == 'paused':
        _finish_batch(cursor, parent_id, 'paused')
    else:
        _refresh_counts(cursor, parent_id)


@retry_on_deadlock
def retry_as_new_batch(batch_id: int, actor: Any) -> dict[str, Any]:
    """Lỗi cấu hình đã sửa ở mẫu tin: tạo lô mới gồm khách lỗi cấu hình (và khách chưa gửi nếu lô đang tạm dừng), dùng nội dung mẫu hiện tại."""
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute('SELECT Status, CreatedBy, ConfirmedBy, TemplateId, FileName, Owner, DepartmentId FROM dbo.ZnsSendBatches WITH (UPDLOCK, ROWLOCK) WHERE Id = %s', [batch_id])
        row = cursor.fetchone()
        if not row or row[0] not in ('partial', 'failed', 'paused'):
            raise MessagingError('Chỉ tạo lô gửi lại từ lô "Gửi một phần", "Thất bại" hoặc "Tạm dừng".')
        _, created_by, confirmed_by, template_id, file_name, owner, department = row
        if not actor.can_retry(owner, created_by, confirmed_by, department):
            raise MessagingError('Chỉ người tạo lô hoặc người có quyền gửi lại mới gửi lại được.')
        cursor.execute(
            f"""
            SELECT Id, RowNo, Phone, Params FROM dbo.ZnsSendRecipients
            WHERE BatchId = %s AND RetriedInBatchId IS NULL AND ({_NEW_BATCH_CLAUSE}) ORDER BY RowNo
            """,
            [batch_id],
        )
        source = cursor.fetchall()
        if not source:
            raise MessagingError('Không có khách lỗi cấu hình nào cần gửi lại.')
        variables = [v for v in load_template(cursor, template_id)['variables'] if v['is_active']]
        names = [v['name'] for v in variables if v['source'] == 'customer']
        # Biến dùng chung mà mẫu không có dữ liệu: giữ giá trị đã gửi. Biến có dữ liệu dùng giá trị hiện tại của mẫu (có thể vừa được sửa).
        sent = json.loads(source[0][3] or '{}')
        fixed = {v['name']: sent.get(v['name']) for v in variables if v['source'] == 'fixed' and not v['default_value'] and sent.get(v['name'])}
        columns = ['Số điện thoại', *names]
        parsed = {
            'sheet': f'Gửi lại từ lô {batch_id}',
            'columns': columns,
            'rows': [{'row_no': r[1], 'values': [r[2], *[(json.loads(r[3] or '{}').get(n) or None) for n in names]]} for r in source],
            'fixed': {},
        }
        new_id = create_draft(parsed, f'gui_lai_lo_{batch_id}_{file_name}', actor.username)
        mapping = {'__phone__': 0, **{n: i + 1 for i, n in enumerate(names)}}
        result = confirm(new_id, template_id, mapping, fixed, actor)
        cursor.execute('UPDATE dbo.ZnsSendBatches SET ParentBatchId = %s WHERE Id = %s', [batch_id, new_id])
        _link_retry(cursor, batch_id, new_id)
        audit.log('zns.retry_new', actor.username, 'batch', new_id, f'Gửi lại từ lô #{batch_id}')
    return {**result, 'parent_batch_id': batch_id}
