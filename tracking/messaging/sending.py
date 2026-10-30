from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

import openpyxl
from django.db import connection, transaction

from ..constants import ZNS_SEND_DELAY_MS
from ..core.sql import rows
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
HISTORY_PAGE_SIZE = 20
DETAIL_PAGE_SIZE = 50
MAX_SQL_PARAMS = 2000
SEND_CHUNK = 50
logger = logging.getLogger(__name__)
_FIXED_KEY_HEADERS = frozenset({'biencodinh', 'bien', 'tenbien', 'variable', 'key'})
_FIXED_VALUE_HEADERS = frozenset({'dulieu', 'giatri', 'value', 'noidung'})
TEMPLATE_CODE_KEY = 'templatecode'
STATUS_LABELS = {
    'draft': 'Nháp',
    'pending': 'Chờ gửi',
    'sending': 'Đang gửi',
    'done': 'Đã gửi',
    'cancelled': 'Đã hủy',
    'invalid': 'Lỗi dữ liệu',
    'sent': 'Đã gửi thành công',
    'failed': 'Gửi thất bại',
    'simulated': 'Chạy thử (không gửi)',
}
SEND_MODE_LABELS = {'dry_run': 'Chạy thử', 'live': 'Gửi thật'}


def _status_label(status: str, send_mode: str | None) -> str:
    if status == 'done' and send_mode == 'dry_run':
        return 'Đã chạy thử'
    return STATUS_LABELS.get(status, status)


def _sheet_rows(ws) -> list[tuple[int, list[Any]]]:
    out = []
    for idx, row in enumerate(ws.iter_rows(), start=1):
        cells = [cell_value(c.value, getattr(c, 'number_format', None)) for c in row]
        if any(c is not None for c in cells):
            out.append((idx, cells))
        if len(out) > MAX_ROWS + 100:
            break
    return out


def _fixed_block(sheet_rows: list[tuple[int, list[Any]]]) -> tuple[dict[str, Any], set[int]]:
    for pos, (_, cells) in enumerate(sheet_rows):
        keys = [normalize_key(c) for c in cells]
        key_col = next((i for i, k in enumerate(keys) if k in _FIXED_KEY_HEADERS), None)
        if key_col is None:
            continue
        value_col = next((i for i in range(key_col + 1, len(keys)) if keys[i] in _FIXED_VALUE_HEADERS), None)
        if value_col is None:
            continue
        fixed, used = {}, {sheet_rows[pos][0]}
        for row_no, row in sheet_rows[pos + 1 :]:
            name = row[key_col] if key_col < len(row) else None
            if name is None:
                break
            fixed[normalize_key(name)] = row[value_col] if value_col < len(row) else None
            used.add(row_no)
        return fixed, used
    return {}, set()


def _customer_table(sheet_rows: list[tuple[int, list[Any]]], skip: set[int]) -> tuple[list[str], list[dict]] | None:
    candidates = [(n, c) for n, c in sheet_rows if n not in skip]
    header_pos = next((i for i, (_, c) in enumerate(candidates[:30]) if any(normalize_key(x) in PHONE_KEYS for x in c)), None)
    if header_pos is None:
        return None
    _, header = candidates[header_pos]
    last = max(i for i, h in enumerate(header) if h is not None)
    columns = [str(h) if h is not None else f'Cột {i + 1}' for i, h in enumerate(header[: last + 1])]
    data = []
    for row_no, cells in candidates[header_pos + 1 :]:
        values = (cells + [None] * len(columns))[: len(columns)]
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


def sheet_rows(ws) -> list[tuple[int, list[Any]]]:
    return _sheet_rows(ws)


def parse_workbook(upload: Any) -> dict[str, Any]:
    wb = open_workbook(upload)
    fixed: dict[str, Any] = {}
    table = None
    try:
        for ws in wb.worksheets:
            sheet_rows = _sheet_rows(ws)
            block, used = _fixed_block(sheet_rows)
            for key, value in block.items():
                fixed.setdefault(key, value)
            if table is None:
                found = _customer_table(sheet_rows, used)
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


def _draft(cursor: Any, batch_id: int) -> dict[str, Any]:
    cursor.execute('SELECT Status, RawData, FileName FROM dbo.ZnsSendBatches WHERE Id = %s', [batch_id])
    row = cursor.fetchone()
    if not row:
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


def _customer_label(variables: list[dict], values: dict[str, Any]) -> str | None:
    if values.get('name'):
        return str(values['name'])
    first = next((v['name'] for v in variables if v['source'] == 'customer' and v['data_type'] == 'text' and values.get(v['name'])), None)
    return str(values[first]) if first else None


def _evaluate(cursor: Any, batch_id: int, template_id: int, raw_mapping: Any, raw_fixed: Any) -> dict[str, Any]:
    draft = _draft(cursor, batch_id)
    template = load_template(cursor, template_id)
    if not template['is_active']:
        raise MessagingError('Mẫu tin đang ngừng hoạt động.')
    variables = [v for v in template['variables'] if v['is_active']]
    columns = draft['columns']
    mapping = _clean_mapping(raw_mapping, variables, columns)
    excel_fixed = draft.get('fixed') or {}
    raw_fixed = raw_fixed if isinstance(raw_fixed, dict) else {}

    fixed_values, fixed_display, fixed_input, fixed_errors = {}, {}, {}, {}
    for v in variables:
        if v['source'] != 'fixed':
            continue
        if v['name'] in raw_fixed:
            given = raw_fixed[v['name']]
        else:
            given = v.get('default_value') or excel_fixed.get(normalize_key(v['name']))
        value, error = coerce(v['data_type'], given)
        fixed_input[v['name']] = display(v['data_type'], value) if value is not None and not error else ('' if given is None else str(given))
        if error:
            fixed_errors[v['name']] = error
        elif value is None and v['is_required']:
            fixed_errors[v['name']] = 'Bắt buộc nhập'
        fixed_values[v['name']] = value
        fixed_display[v['name']] = display(v['data_type'], value)

    mapping_errors = []
    if mapping['__phone__'] is None:
        mapping_errors.append('Chưa chọn cột Số điện thoại.')
    for v in variables:
        if v['source'] == 'customer' and v['is_required'] and mapping.get(v['name']) is None:
            mapping_errors.append(f'Chưa chọn cột cho biến <{v["name"]}> (bắt buộc).')
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
            elif value is None and v['is_required'] and col is not None:
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
                '_values': values,
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


def evaluate(batch_id: int, template_id: int, mapping: Any, fixed: Any) -> dict[str, Any]:
    with connection.cursor() as cursor:
        result = _evaluate(cursor, batch_id, template_id, mapping, fixed)
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


def confirm(batch_id: int, template_id: int, mapping: Any, fixed: Any, user: str) -> dict[str, Any]:
    """Chốt danh sách + tham số từng khách, chuyển lô sang "Đang gửi" và gửi ở luồng nền sau khi commit."""
    mode = provider.send_mode()
    with transaction.atomic(), connection.cursor() as cursor:
        result = _evaluate(cursor, batch_id, template_id, mapping, fixed)
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
        cursor.execute("SELECT RowNo, Id FROM dbo.ZnsSendRecipients WHERE BatchId = %s AND Status = 'pending'", [batch_id])
        ids = dict(cursor.fetchall())
        names = [v['name'] for v in result['variables']]
        data_rows = [[batch_id, ids[r['row_no']], r['phone'], *[r['_values'].get(n) for n in names]] for r in result['rows'] if r['valid']]
        _insert_many(cursor, f'dbo.[{template["data_table"]}]', ['BatchId', 'RecipientId', 'Phone', *[f'[{n}]' for n in names]], data_rows)
        fixed_json = {v['name']: to_json(v['data_type'], result['fixed_values'][v['name']]) for v in result['variables'] if v['source'] == 'fixed'}
        mapping_json = {k: (result['draft']['columns'][i] if i is not None else None) for k, i in result['mapping'].items()}
        summary = result['summary']
        cursor.execute(
            """
            UPDATE dbo.ZnsSendBatches SET TemplateId = %s, Owner = %s, ColumnMapping = %s, FixedValues = %s, RawData = NULL,
                   TotalRows = %s, ValidRows = %s, InvalidRows = %s, ConfirmedBy = %s, ConfirmedAt = SYSUTCDATETIME(),
                   SendMode = %s, SentBy = %s, SendStartedAt = SYSUTCDATETIME()
            WHERE Id = %s
            """,
            [template['id'], template['owner'], json.dumps(mapping_json, ensure_ascii=False), json.dumps(fixed_json, ensure_ascii=False),
             summary['total'], summary['valid'], summary['invalid'], user, mode, user, batch_id],
        )
        transaction.on_commit(lambda: _start_thread(batch_id))
    return {'batch_id': batch_id, 'data_table': template['data_table'], 'send_mode': mode, 'send_mode_label': SEND_MODE_LABELS[mode], **summary}


def _pages(total: int, size: int, page: int) -> tuple[int, int]:
    pages = max(1, -(-total // size))
    return min(max(1, page), pages), pages


def list_batches(page: int = 1) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM dbo.ZnsSendBatches WHERE Status <> 'draft'")
        total = cursor.fetchone()[0]
        page, pages = _pages(total, HISTORY_PAGE_SIZE, page)
        cursor.execute(
            f"""
            SELECT b.Id AS id, b.FileName AS file_name, b.Owner AS owner, b.Status AS status,
                   b.TotalRows AS total_rows, b.ValidRows AS valid_rows, b.InvalidRows AS invalid_rows,
                   b.CreatedBy AS created_by, b.ConfirmedAt AS confirmed_at, t.Name AS template_name, t.ZnsCode AS zns_code,
                   b.SendMode AS send_mode, b.SentRows AS sent_rows, b.FailedRows AS failed_rows
            FROM dbo.ZnsSendBatches b LEFT JOIN dbo.ZnsTemplates t ON t.Id = b.TemplateId
            WHERE b.Status <> 'draft'
            ORDER BY b.Id DESC
            OFFSET {(page - 1) * HISTORY_PAGE_SIZE} ROWS FETCH NEXT {HISTORY_PAGE_SIZE} ROWS ONLY
            """
        )
        data = rows(cursor)
    for r in data:
        r['confirmed_at'] = iso_utc(r['confirmed_at'])
        r['status_label'] = _status_label(r['status'], r['send_mode'])
    return {'data': data, 'page': page, 'pages': pages, 'page_size': HISTORY_PAGE_SIZE, 'total': total}


def _batch(cursor: Any, batch_id: int) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT b.Id, b.FileName, b.Owner, b.Status, b.TotalRows, b.ValidRows, b.InvalidRows, b.FixedValues, b.ColumnMapping,
               b.CreatedBy, b.ConfirmedAt, t.Name, t.ZnsCode, b.SendMode, b.SendFinishedAt, b.SentRows, b.FailedRows
        FROM dbo.ZnsSendBatches b LEFT JOIN dbo.ZnsTemplates t ON t.Id = b.TemplateId
        WHERE b.Id = %s AND b.Status <> 'draft'
        """,
        [batch_id],
    )
    row = cursor.fetchone()
    if not row:
        raise MessagingError('Không tìm thấy lô gửi.')
    keys = ('id', 'file_name', 'owner', 'status', 'total_rows', 'valid_rows', 'invalid_rows', 'fixed', 'mapping', 'created_by', 'confirmed_at', 'template_name', 'zns_code', 'send_mode', 'finished_at', 'sent_rows', 'failed_rows')
    batch = dict(zip(keys, row))
    batch['fixed'] = json.loads(batch['fixed'] or '{}')
    batch['mapping'] = json.loads(batch['mapping'] or '{}')
    batch['confirmed_at'] = iso_utc(batch['confirmed_at'])
    batch['finished_at'] = iso_utc(batch['finished_at'])
    batch['send_mode_label'] = SEND_MODE_LABELS.get(batch['send_mode'] or '')
    batch['status_label'] = _status_label(batch['status'], batch['send_mode'])
    return batch


def _recipients(cursor: Any, batch_id: int, page: int | None = None) -> list[dict[str, Any]]:
    paging = f'OFFSET {(int(page) - 1) * DETAIL_PAGE_SIZE} ROWS FETCH NEXT {DETAIL_PAGE_SIZE} ROWS ONLY' if page else ''
    cursor.execute(
        f"""
        SELECT RowNo AS row_no, Phone AS phone, CustomerName AS customer, Content AS content, Status AS status,
               ErrorMessage AS error, SentAt AS sent_at
        FROM dbo.ZnsSendRecipients WHERE BatchId = %s ORDER BY RowNo {paging}
        """,
        [batch_id],
    )
    data = rows(cursor)
    for r in data:
        r['status_label'] = STATUS_LABELS.get(r['status'], r['status'])
        r['sent_at'] = iso_utc(r['sent_at'])
    return data


def batch_detail(batch_id: int, page: int = 1) -> dict[str, Any]:
    with connection.cursor() as cursor:
        batch = _batch(cursor, batch_id)
        page, pages = _pages(batch['total_rows'], DETAIL_PAGE_SIZE, page)
        batch['recipients'] = _recipients(cursor, batch_id, page)
    return {**batch, 'page': page, 'pages': pages, 'page_size': DETAIL_PAGE_SIZE}


def batch_export_rows(batch_id: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with connection.cursor() as cursor:
        return _batch(cursor, batch_id), _recipients(cursor, batch_id)


def cancel_batch(batch_id: int, user: str, is_staff: bool) -> None:
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute('SELECT Status, CreatedBy, ConfirmedBy FROM dbo.ZnsSendBatches WHERE Id = %s', [batch_id])
        row = cursor.fetchone()
        if not row or row[0] not in ('pending', 'sending'):
            raise MessagingError('Chỉ hủy được lô đang "Chờ gửi" hoặc "Đang gửi".')
        if not _can_manage(user, is_staff, row[1], row[2]):
            raise MessagingError('Chỉ người tạo / xác nhận lô hoặc quản trị viên được hủy.')
        cursor.execute(
            "UPDATE dbo.ZnsSendBatches SET Status = 'cancelled', CancelledBy = %s, CancelledAt = SYSUTCDATETIME() WHERE Id = %s AND Status IN ('pending', 'sending')",
            [user, batch_id],
        )
        cursor.execute("UPDATE dbo.ZnsSendRecipients SET Status = 'cancelled' WHERE BatchId = %s AND Status = 'pending'", [batch_id])


def _can_manage(user: str, is_staff: bool, created_by: str | None, confirmed_by: str | None) -> bool:
    return is_staff or user in (created_by, confirmed_by)


def _start_thread(batch_id: int) -> None:
    threading.Thread(target=_run_in_thread, args=(batch_id,), name=f'zns-send-{batch_id}', daemon=True).start()


def _batch_status(batch_id: int) -> str | None:
    with connection.cursor() as cursor:
        cursor.execute('SELECT Status FROM dbo.ZnsSendBatches WHERE Id = %s', [batch_id])
        row = cursor.fetchone()
    return row[0] if row else None


def _run_in_thread(batch_id: int) -> None:
    try:
        run_send(batch_id)
    except Exception:
        logger.exception('ZNS: lô %s dừng giữa chừng, giữ trạng thái "Đang gửi" (chạy tiếp: manage.py zns_send_batch %s)', batch_id, batch_id)
    finally:
        connection.close()


def run_send(batch_id: int) -> dict[str, int]:
    """Gửi lần lượt khách "Chờ gửi" của lô đang "Đang gửi". Chạy lại được nếu bị dừng giữa chừng."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT b.Status, b.Owner, b.SendMode, t.ZnsCode
            FROM dbo.ZnsSendBatches b JOIN dbo.ZnsTemplates t ON t.Id = b.TemplateId WHERE b.Id = %s
            """,
            [batch_id],
        )
        row = cursor.fetchone()
    if not row or row[0] != 'sending':
        raise MessagingError('Lô không ở trạng thái "Đang gửi".')
    owner, mode, template_code = row[1], row[2], row[3]
    if mode != provider.send_mode():
        raise MessagingError(f'Lô bắt đầu ở chế độ {mode}, server đang ở chế độ {provider.send_mode()}: không tự đổi chế độ giữa chừng.')
    counts = {'sent': 0, 'failed': 0, 'simulated': 0}
    while True:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT TOP {SEND_CHUNK} Id, Phone, Params FROM dbo.ZnsSendRecipients WHERE BatchId = %s AND Status = 'pending' ORDER BY RowNo",
                [batch_id],
            )
            chunk = cursor.fetchall()
        if not chunk:
            break
        for recipient_id, phone, params in chunk:
            if _batch_status(batch_id) != 'sending':
                logger.info('ZNS: lô %s đã bị hủy giữa chừng %s', batch_id, counts)
                return counts
            if params is None:
                result = provider.SendResult(ok=False, error='Thiếu tham số (lô xác nhận trước khi có chức năng gửi), hãy tạo lại lô.')
            else:
                result = provider.send(owner, phone, template_code, json.loads(params))
            status = 'simulated' if result.simulated else ('sent' if result.ok else 'failed')
            counts[status] += 1
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE dbo.ZnsSendRecipients SET Status = %s, ErrorMessage = %s, ApiResponse = %s, ZaloMsgId = %s,
                           SentAt = CASE WHEN %s = 'sent' THEN SYSUTCDATETIME() ELSE SentAt END
                    WHERE Id = %s AND Status = 'pending'
                    """,
                    [status, result.error, result.response, result.msg_id, status, recipient_id],
                )
                if cursor.rowcount == 1:
                    column = 'FailedRows' if status == 'failed' else 'SentRows'
                    cursor.execute(f'UPDATE dbo.ZnsSendBatches SET {column} = {column} + 1 WHERE Id = %s', [batch_id])
            if not result.simulated and ZNS_SEND_DELAY_MS:
                time.sleep(ZNS_SEND_DELAY_MS / 1000)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE dbo.ZnsSendBatches SET Status = 'done', SendFinishedAt = SYSUTCDATETIME() WHERE Id = %s AND Status = 'sending'", [batch_id]
        )
    logger.info('ZNS: xong lô %s (%s) %s', batch_id, mode, counts)
    return counts
