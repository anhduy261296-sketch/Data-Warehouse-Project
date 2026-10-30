from __future__ import annotations

import re
from typing import Any

from django.db import IntegrityError, connection, transaction

from ..core.sql import rows
from . import schema
from .values import DATA_TYPES, OWNERS, SOURCES, MessagingError, coerce, display, iso_utc, placeholders

NAME_MAX_LEN = 200
CONTENT_MAX_LEN = 2000
ZNS_CODE_RE = re.compile(r'^[A-Za-z0-9_.-]{1,50}$')
CHANGE_LOG_LIMIT = 100
DEFAULT_VARIABLES = (
    {'name': 'name', 'label': 'Tên khách hàng', 'data_type': 'text', 'source': 'customer', 'is_required': True, 'sample': 'Nguyễn Văn A'},
    {'name': 'giam', 'label': 'Giảm', 'data_type': 'text', 'source': 'fixed', 'is_required': True, 'sample': '5%'},
    {'name': 'voucher_name', 'label': 'Tên voucher', 'data_type': 'text', 'source': 'fixed', 'is_required': True, 'sample': 'Ghé thăm cửa hàng-Nhận ưu đãi'},
    {'name': 'start_date', 'label': 'Ngày bắt đầu', 'data_type': 'date', 'source': 'fixed', 'is_required': False, 'sample': '01/10/2026'},
    {'name': 'expired_date', 'label': 'Ngày hết hạn', 'data_type': 'datetime', 'source': 'fixed', 'is_required': False, 'sample': '22:00 31/12/2026'},
    {'name': 'voucher_code', 'label': 'Mã voucher', 'data_type': 'text', 'source': 'fixed', 'is_required': False, 'sample': 'AWG0926'},
    {'name': 'condition', 'label': 'Điều kiện', 'data_type': 'text', 'source': 'fixed', 'is_required': False, 'sample': 'Tất các sản phẩm,trừ Outlet'},
)
DEFAULT_CONTENT = (
    'Thân Chào Quý khách hàng <name>,\n\n'
    'Mời Quý khách ghé thăm Alpha Works Showroom - A007 đường D9 tòa Sarica, Khu Đô Thị Sala, Phường An Khánh, '
    'Thành Phố Hồ Chí Minh, khám phá công nghệ và nhận ngay ưu đãi giảm <giam> tại cửa hàng Alpha Works'
)
_TYPE_LABELS = {'text': 'Text', 'number': 'Number', 'date': 'Date', 'datetime': 'Datetime'}
_SOURCE_LABELS = {'customer': 'theo khách hàng', 'fixed': 'cố định cho lô'}


def list_templates(owner: str | None = None, active_only: bool = False) -> list[dict[str, Any]]:
    where, args = ['1 = 1'], []
    if owner:
        where.append('t.Owner = %s')
        args.append(owner)
    if active_only:
        where.append('t.IsActive = 1')
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT t.Id AS id, t.Name AS name, t.ZnsCode AS zns_code, t.Owner AS owner, t.IsActive AS is_active,
                   t.CreatedBy AS created_by, t.CreatedAt AS created_at, t.UpdatedBy AS updated_by, t.UpdatedAt AS updated_at,
                   (SELECT COUNT(*) FROM dbo.ZnsTemplateVariables v WHERE v.TemplateId = t.Id AND v.IsActive = 1) AS variable_count,
                   (SELECT COUNT(*) FROM dbo.ZnsSendBatches b WHERE b.TemplateId = t.Id AND b.Status NOT IN ('draft', 'cancelled')) AS batch_count,
                   (SELECT ISNULL(SUM(b.ValidRows), 0) FROM dbo.ZnsSendBatches b WHERE b.TemplateId = t.Id AND b.Status NOT IN ('draft', 'cancelled')) AS message_count
            FROM dbo.ZnsTemplates t
            WHERE {' AND '.join(where)}
            ORDER BY t.IsActive DESC, t.UpdatedAt DESC
            """,
            args,
        )
        data = rows(cursor)
    for r in data:
        r['is_active'] = bool(r['is_active'])
        r['created_at'], r['updated_at'] = iso_utc(r['created_at']), iso_utc(r['updated_at'])
    return data


def load_template(cursor: Any, template_id: int) -> dict[str, Any]:
    cursor.execute(
        'SELECT Id, Name, ZnsCode, Owner, Content, DataTable, IsActive, CreatedBy, CreatedAt, UpdatedBy, UpdatedAt FROM dbo.ZnsTemplates WHERE Id = %s',
        [template_id],
    )
    row = cursor.fetchone()
    if not row:
        raise MessagingError('Không tìm thấy mẫu tin.')
    keys = ('id', 'name', 'zns_code', 'owner', 'content', 'data_table', 'is_active', 'created_by', 'created_at', 'updated_by', 'updated_at')
    template = dict(zip(keys, row))
    template['is_active'] = bool(template['is_active'])
    cursor.execute(
        """
        SELECT Id AS id, Name AS name, Label AS label, DataType AS data_type, Source AS source,
               IsRequired AS is_required, IsActive AS is_active, SortOrder AS sort_order, DefaultValue AS default_value
        FROM dbo.ZnsTemplateVariables WHERE TemplateId = %s ORDER BY SortOrder, Id
        """,
        [template_id],
    )
    template['variables'] = rows(cursor)
    for v in template['variables']:
        v['is_required'], v['is_active'] = bool(v['is_required']), bool(v['is_active'])
    return template


def get_template(template_id: int) -> dict[str, Any]:
    with connection.cursor() as cursor:
        template = load_template(cursor, template_id)
        with_data = schema.columns_with_data(cursor, template['data_table'], [v['name'] for v in template['variables']])
        for v in template['variables']:
            v['has_data'] = v['name'] in with_data
        cursor.execute(
            f"""
            SELECT TOP {CHANGE_LOG_LIMIT} VariableName AS variable, Action AS action, Detail AS detail, ChangedBy AS changed_by, ChangedAt AS changed_at
            FROM dbo.ZnsTemplateChangeLog WHERE TemplateId = %s ORDER BY ChangedAt DESC, Id DESC
            """,
            [template_id],
        )
        template['changes'] = rows(cursor)
    for c in template['changes']:
        c['changed_at'] = iso_utc(c['changed_at'])
    template['created_at'], template['updated_at'] = iso_utc(template['created_at']), iso_utc(template['updated_at'])
    return template


def _clean_text(value: Any, field: str, max_len: int, required: bool = True) -> str:
    text = str(value or '').strip()
    if required and not text:
        raise MessagingError(f'Vui lòng nhập {field}.')
    if len(text) > max_len:
        raise MessagingError(f'{field.capitalize()} tối đa {max_len} ký tự.')
    return text


def _clean_variables(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise MessagingError('Danh sách biến không hợp lệ.')
    variables, seen = [], set()
    for order, item in enumerate(raw, start=1):
        name = str(item.get('name') or '').strip()
        error = schema.validate_name(name)
        if error:
            raise MessagingError(f'Biến "{name or "(trống)"}": {error}.')
        if name in seen:
            raise MessagingError(f'Biến "{name}" bị trùng tên.')
        seen.add(name)
        data_type, source = item.get('data_type'), item.get('source')
        if data_type not in DATA_TYPES:
            raise MessagingError(f'Biến "{name}": kiểu dữ liệu không hợp lệ.')
        if source not in SOURCES:
            raise MessagingError(f'Biến "{name}": nguồn dữ liệu không hợp lệ.')
        default_value = None
        if source == 'fixed':
            value, value_error = coerce(data_type, item.get('default_value'))
            if value_error:
                raise MessagingError(f'Biến "{name}": dữ liệu {value_error[:1].lower()}{value_error[1:]}.')
            default_value = display(data_type, value) or None
            if default_value is None and item.get('is_required') and item.get('is_active', True) is not False:
                raise MessagingError(f'Biến "{name}": bắt buộc nhưng chưa nhập dữ liệu.')
        variables.append(
            {
                'id': int(item['id']) if item.get('id') else None,
                'name': name,
                'label': _clean_text(item.get('label'), 'nhãn biến', 200, required=False) or None,
                'data_type': data_type,
                'source': source,
                'is_required': bool(item.get('is_required')),
                'default_value': default_value,
                'is_active': item.get('is_active', True) is not False,
                'sort_order': order,
            }
        )
    return variables


def _clean(payload: dict[str, Any]) -> dict[str, Any]:
    data = {
        'name': _clean_text(payload.get('name'), 'tên mẫu tin', NAME_MAX_LEN),
        'zns_code': _clean_text(payload.get('zns_code'), 'mã', 50),
        'owner': payload.get('owner'),
        'content': _clean_text(payload.get('content'), 'nội dung tin nhắn', CONTENT_MAX_LEN),
        'variables': _clean_variables(payload.get('variables') or []),
        'is_active': payload.get('is_active', True) is not False,
    }
    if not ZNS_CODE_RE.match(data['zns_code']):
        raise MessagingError('Mã chỉ gồm chữ, số, dấu _ . - (tối đa 50 ký tự).')
    if data['owner'] not in OWNERS:
        raise MessagingError('Vui lòng chọn chủ hàng PGI hoặc AWG.')
    active = {v['name'] for v in data['variables'] if v['is_active']}
    unknown = [p for p in placeholders(data['content']) if p not in active]
    if unknown:
        raise MessagingError(f'Nội dung dùng biến chưa khai báo hoặc đang ngừng dùng: {", ".join(f"<{u}>" for u in unknown)}.')
    return data


def _log(cursor: Any, template_id: int, action: str, detail: str, user: str, variable: str | None = None) -> None:
    cursor.execute(
        'INSERT INTO dbo.ZnsTemplateChangeLog (TemplateId, VariableName, Action, Detail, ChangedBy) VALUES (%s, %s, %s, %s, %s)',
        [template_id, variable, action, detail[:1000], user],
    )


def _insert_variable(cursor: Any, template_id: int, v: dict[str, Any]) -> None:
    cursor.execute(
        """
        INSERT INTO dbo.ZnsTemplateVariables (TemplateId, Name, Label, DataType, Source, IsRequired, DefaultValue, IsActive, SortOrder)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [template_id, v['name'], v['label'], v['data_type'], v['source'], v['is_required'], v['default_value'], v['is_active'], v['sort_order']],
    )


def _describe(v: dict[str, Any]) -> str:
    required = 'bắt buộc' if v['is_required'] else 'không bắt buộc'
    return f'{_TYPE_LABELS[v["data_type"]]}, {_SOURCE_LABELS[v["source"]]}, {required}'


def _create(cursor: Any, data: dict[str, Any], user: str) -> int:
    cursor.execute(
        """
        INSERT INTO dbo.ZnsTemplates (Name, ZnsCode, Owner, Content, IsActive, CreatedBy, UpdatedBy)
        OUTPUT INSERTED.Id VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        [data['name'], data['zns_code'], data['owner'], data['content'], data['is_active'], user, user],
    )
    template_id = int(cursor.fetchone()[0])
    for v in data['variables']:
        _insert_variable(cursor, template_id, v)
    table = schema.create_data_table(cursor, template_id, data['variables'])
    cursor.execute('UPDATE dbo.ZnsTemplates SET DataTable = %s WHERE Id = %s', [table, template_id])
    _log(cursor, template_id, 'CREATE_TEMPLATE', f'Tạo mẫu {data["zns_code"]} ({data["owner"]}), bảng {table}, {len(data["variables"])} biến', user)
    return template_id


def _update(cursor: Any, template_id: int, data: dict[str, Any], user: str) -> None:
    current = load_template(cursor, template_id)
    table = current['data_table']
    changed = [
        f'{label}: "{current[key]}" → "{data[key]}"'
        for key, label in (('name', 'Tên'), ('zns_code', 'Mã ZNS'), ('owner', 'Chủ hàng'))
        if current[key] != data[key]
    ]
    if current['content'] != data['content']:
        changed.append('Sửa nội dung tin nhắn')
    if changed:
        cursor.execute(
            'UPDATE dbo.ZnsTemplates SET Name = %s, ZnsCode = %s, Owner = %s, Content = %s, UpdatedBy = %s, UpdatedAt = SYSUTCDATETIME() WHERE Id = %s',
            [data['name'], data['zns_code'], data['owner'], data['content'], user, template_id],
        )
        _log(cursor, template_id, 'UPDATE_TEMPLATE', '; '.join(changed), user)
    existing = {v['id']: v for v in current['variables']}
    by_name = {v['name']: v for v in current['variables']}
    with_data = schema.columns_with_data(cursor, table, list(by_name))
    submitted_ids = set()
    touched = bool(changed)
    for v in data['variables']:
        old = existing.get(v['id']) if v['id'] else by_name.get(v['name'])
        if old is None:
            if v['name'] in by_name:
                raise MessagingError(f'Biến "{v["name"]}" đã tồn tại.')
            _insert_variable(cursor, template_id, v)
            schema.add_column(cursor, table, v['name'], v['data_type'])
            _log(cursor, template_id, 'ADD_VARIABLE', f'Thêm biến: {_describe(v)}; thêm cột [{v["name"]}] vào {table}', user, v['name'])
            touched = True
            continue
        submitted_ids.add(old['id'])
        if old['name'] != v['name']:
            raise MessagingError(f'Không đổi tên biến "{old["name"]}" được (tránh mất dữ liệu cũ). Hãy ngừng dùng và thêm biến mới.')
        notes = []
        if old['data_type'] != v['data_type']:
            if old['name'] in with_data:
                raise MessagingError(f'Biến "{old["name"]}" đã có dữ liệu gửi, không đổi kiểu được. Hãy thêm biến mới.')
            schema.change_column_type(cursor, table, old['name'], v['data_type'])
            notes.append(f'kiểu {_TYPE_LABELS[old["data_type"]]} → {_TYPE_LABELS[v["data_type"]]}')
        if old['source'] != v['source']:
            notes.append(f'nguồn {_SOURCE_LABELS[old["source"]]} → {_SOURCE_LABELS[v["source"]]}')
        if old['is_required'] != v['is_required']:
            notes.append('bắt buộc' if v['is_required'] else 'bỏ bắt buộc')
        if (old['default_value'] or None) != v['default_value']:
            notes.append(f'dữ liệu "{old["default_value"] or ""}" → "{v["default_value"] or ""}"')
        if (old['label'] or None) != v['label']:
            notes.append(f'nhãn "{old["label"] or ""}" → "{v["label"] or ""}"')
        if old['is_active'] != v['is_active']:
            notes.append('dùng lại' if v['is_active'] else 'ngừng dùng (giữ cột và dữ liệu)')
        if notes or old['sort_order'] != v['sort_order']:
            cursor.execute(
                """
                UPDATE dbo.ZnsTemplateVariables SET Label = %s, DataType = %s, Source = %s, IsRequired = %s, DefaultValue = %s,
                       IsActive = %s, SortOrder = %s, UpdatedAt = SYSUTCDATETIME() WHERE Id = %s
                """,
                [v['label'], v['data_type'], v['source'], v['is_required'], v['default_value'], v['is_active'], v['sort_order'], old['id']],
            )
            touched = True
        if notes:
            action = 'DISABLE_VARIABLE' if not v['is_active'] and old['is_active'] else 'UPDATE_VARIABLE'
            _log(cursor, template_id, action, '; '.join(notes), user, old['name'])
    for old in current['variables']:
        if old['id'] in submitted_ids:
            continue
        if old['name'] not in with_data:
            cursor.execute('DELETE FROM dbo.ZnsTemplateVariables WHERE Id = %s', [old['id']])
            schema.drop_column(cursor, table, old['name'])
            _log(cursor, template_id, 'DELETE_VARIABLE', f'Xóa biến (chưa có dữ liệu gửi); xóa cột [{old["name"]}] khỏi {table}', user, old['name'])
            touched = True
        elif old['is_active']:
            cursor.execute('UPDATE dbo.ZnsTemplateVariables SET IsActive = 0, UpdatedAt = SYSUTCDATETIME() WHERE Id = %s', [old['id']])
            _log(cursor, template_id, 'DISABLE_VARIABLE', 'ngừng dùng vì đã có dữ liệu gửi (giữ cột và dữ liệu)', user, old['name'])
            touched = True
    if touched and not changed:
        cursor.execute('UPDATE dbo.ZnsTemplates SET UpdatedBy = %s, UpdatedAt = SYSUTCDATETIME() WHERE Id = %s', [user, template_id])


def save_template(payload: dict[str, Any], user: str) -> int:
    data = _clean(payload)
    template_id = int(payload['id']) if payload.get('id') else None
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            if template_id:
                _update(cursor, template_id, data, user)
            else:
                template_id = _create(cursor, data, user)
    except IntegrityError as exc:
        if 'UQ_ZnsTemplates_Owner_Code' in str(exc):
            raise MessagingError(f'Mã template {data["zns_code"]} đã có cho chủ hàng {data["owner"]}.') from exc
        raise
    return template_id


def set_active(template_id: int, active: bool, user: str) -> None:
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            'UPDATE dbo.ZnsTemplates SET IsActive = %s, UpdatedBy = %s, UpdatedAt = SYSUTCDATETIME() WHERE Id = %s AND IsActive <> %s',
            [active, user, template_id, active],
        )
        if cursor.rowcount:
            _log(cursor, template_id, 'ACTIVATE' if active else 'DEACTIVATE', 'Chuyển sang Hoạt động' if active else 'Chuyển sang Ngừng hoạt động', user)
