from __future__ import annotations

import re
from typing import Any

from django.db import IntegrityError, connection, transaction

from ..core import audit
from ..core.sql import rows
from . import schema
from .values import OWNERS, SOURCES, MessagingError, coerce, display, iso_utc, placeholders

NAME_MAX_LEN = 200
CONTENT_MAX_LEN = 2000
ZNS_CODE_RE = re.compile(r'^[A-Za-z0-9_.-]{1,50}$')
CHANGE_LOG_LIMIT = 100
DEFAULT_VARIABLES = (
    {'name': 'name', 'label': 'Tên khách hàng', 'data_type': 'text', 'source': 'customer', 'sample': 'Nguyễn Văn A'},
    {'name': 'giam', 'label': 'Giảm', 'data_type': 'text', 'source': 'fixed', 'sample': '5%'},
    {'name': 'voucher_name', 'label': 'Tên voucher', 'data_type': 'text', 'source': 'fixed', 'sample': 'Ghé thăm cửa hàng-Nhận ưu đãi'},
    {'name': 'start_date', 'label': 'Ngày bắt đầu', 'data_type': 'text', 'source': 'fixed', 'sample': '01/10/2026'},
    {'name': 'expired_date', 'label': 'Ngày hết hạn', 'data_type': 'text', 'source': 'fixed', 'sample': '22:00 31/12/2026'},
    {'name': 'voucher_code', 'label': 'Mã voucher', 'data_type': 'text', 'source': 'fixed', 'sample': 'AWG0926'},
    {'name': 'condition', 'label': 'Điều kiện', 'data_type': 'text', 'source': 'fixed', 'sample': 'Tất các sản phẩm,trừ Outlet'},
)
DEFAULT_CONTENT = (
    'Thân Chào Quý khách hàng <name>,\n\n'
    'Mời Quý khách ghé thăm Alpha Works Showroom - A007 đường D9 tòa Sarica, Khu Đô Thị Sala, Phường An Khánh, '
    'Thành Phố Hồ Chí Minh, khám phá công nghệ và nhận ngay ưu đãi giảm <giam> tại cửa hàng Alpha Works'
)


def list_templates(owner: str | None = None, sendable_only: bool = False) -> list[dict[str, Any]]:
    where, args = ['t.DeletedAt IS NULL'], []
    if owner:
        where.append('t.Owner = %s')
        args.append(owner)
    if sendable_only:
        where.append("t.IsActive = 1 AND t.ApprovalStatus = 'approved'")
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT t.Id AS id, t.Name AS name, t.ZnsCode AS zns_code, t.Owner AS owner, t.IsActive AS is_active,
                   t.ApprovalStatus AS approval_status, t.SubmittedBy AS submitted_by, t.RejectReason AS reject_reason,
                   t.DepartmentId AS department_id, (SELECT g.name FROM dbo.auth_group g WHERE g.id = t.DepartmentId) AS department_name,
                   t.CreatedBy AS created_by, t.CreatedAt AS created_at, t.UpdatedBy AS updated_by, t.UpdatedAt AS updated_at,
                   (SELECT COUNT(*) FROM dbo.ZnsTemplateVariables v WHERE v.TemplateId = t.Id AND v.IsActive = 1) AS variable_count,
                   (SELECT COUNT(*) FROM dbo.ZnsSendBatches b WHERE b.TemplateId = t.Id AND b.Status NOT IN ('draft', 'cancelled')) AS batch_count,
                   (SELECT ISNULL(SUM(b.ValidRows), 0) FROM dbo.ZnsSendBatches b WHERE b.TemplateId = t.Id AND b.Status NOT IN ('draft', 'cancelled')) AS message_count,
                   CASE WHEN EXISTS (SELECT 1 FROM dbo.ZnsSendBatches b WHERE b.TemplateId = t.Id AND b.Status <> 'draft') THEN 1 ELSE 0 END AS has_batches
            FROM dbo.ZnsTemplates t
            WHERE {' AND '.join(where)}
            ORDER BY t.IsActive DESC, t.UpdatedAt DESC
            """,
            args,
        )
        data = rows(cursor)
    for r in data:
        r['is_active'], r['has_batches'] = bool(r['is_active']), bool(r['has_batches'])
        r['created_at'], r['updated_at'] = iso_utc(r['created_at']), iso_utc(r['updated_at'])
    return data


def load_template(cursor: Any, template_id: int) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT Id, Name, ZnsCode, Owner, Content, IsActive, CreatedBy, CreatedAt, UpdatedBy, UpdatedAt,
               ApprovalStatus, SubmittedBy, ApprovedBy, ApprovedAt, RejectedBy, RejectReason,
               DepartmentId, (SELECT g.name FROM dbo.auth_group g WHERE g.id = DepartmentId)
        FROM dbo.ZnsTemplates WHERE Id = %s AND DeletedAt IS NULL
        """,
        [template_id],
    )
    row = cursor.fetchone()
    if not row:
        raise MessagingError('Không tìm thấy mẫu tin.')
    keys = ('id', 'name', 'zns_code', 'owner', 'content', 'is_active', 'created_by', 'created_at', 'updated_by', 'updated_at',
            'approval_status', 'submitted_by', 'approved_by', 'approved_at', 'rejected_by', 'reject_reason',
            'department_id', 'department_name')
    template = dict(zip(keys, row))
    template['is_active'] = bool(template['is_active'])
    template['approved_at'] = iso_utc(template['approved_at'])
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


def _has_batches(cursor: Any, template_id: int) -> bool:
    cursor.execute("SELECT COUNT(*) FROM dbo.ZnsSendBatches WHERE TemplateId = %s AND Status <> 'draft'", [template_id])
    return cursor.fetchone()[0] > 0


def get_template(template_id: int) -> dict[str, Any]:
    with connection.cursor() as cursor:
        template = load_template(cursor, template_id)
        template['code_locked'] = _has_batches(cursor, template_id)
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
        # Người dùng chỉ nhập dữ liệu. Biến Số của mẫu cũ giữ cách trình bày 50.000 nếu vẫn là số; còn lại là văn bản, ngày tự chuẩn hóa.
        source = item.get('source')
        if source not in SOURCES:
            raise MessagingError(f'Biến "{name}": nguồn dữ liệu không hợp lệ.')
        given = item.get('default_value') if source == 'fixed' else None
        data_type = 'number' if item.get('data_type') == 'number' else 'text'
        value, value_error = coerce(data_type, given)
        if value_error and data_type == 'number':
            data_type = 'text'
            value, value_error = coerce(data_type, given)
        if value_error:
            raise MessagingError(f'Biến "{name}": dữ liệu {value_error[:1].lower()}{value_error[1:]}.')
        default_value = display(data_type, value) or None
        variables.append(
            {
                'id': int(item['id']) if item.get('id') else None,
                'name': name,
                'label': _clean_text(item.get('label'), 'nhãn biến', 200, required=False) or None,
                'data_type': data_type,
                'source': source,
                'is_required': True,
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
        'department_id': payload.get('department_id'),
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
        [template_id, variable, action, detail, user],
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
    if v['source'] == 'customer':
        return 'theo khách hàng'
    return f'dữ liệu "{v["default_value"]}"' if v['default_value'] else 'dùng chung, nhập khi gửi'


def _create(cursor: Any, data: dict[str, Any], user: str) -> int:
    cursor.execute(
        """
        INSERT INTO dbo.ZnsTemplates (Name, ZnsCode, Owner, Content, IsActive, CreatedBy, UpdatedBy, ApprovalStatus, SubmittedBy, DepartmentId)
        OUTPUT INSERTED.Id VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s)
        """,
        [data['name'], data['zns_code'], data['owner'], data['content'], data['is_active'], user, user, user, data['department_id']],
    )
    template_id = int(cursor.fetchone()[0])
    for v in data['variables']:
        _insert_variable(cursor, template_id, v)
    _log(cursor, template_id, 'CREATE_TEMPLATE', f'Tạo mẫu {data["zns_code"]} ({data["owner"]}), {len(data["variables"])} biến', user)
    audit.log('template.create', user, 'template', data['zns_code'], f'{data["name"]} · {data["owner"]} · {len(data["variables"])} biến', data['department_id'])
    return template_id


def _update(cursor: Any, template_id: int, data: dict[str, Any], user: str) -> None:
    current = load_template(cursor, template_id)
    # Gửi lại trên lô cũ dùng mã của mẫu: đổi mã sẽ gửi sai mẫu Incom với biến cũ.
    if current['zns_code'] != data['zns_code'] and _has_batches(cursor, template_id):
        raise MessagingError('Mẫu đã có lô gửi nên không đổi được mã. Hãy tạo mẫu mới nếu cần dùng mã khác.')
    changed = [
        f'{label}: "{current[key]}" → "{data[key]}"'
        for key, label in (('name', 'Tên'), ('zns_code', 'Mã ZNS'), ('owner', 'Chủ hàng'))
        if current[key] != data[key]
    ]
    if current['content'] != data['content']:
        changed.append(f'Nội dung: "{current["content"]}" → "{data["content"]}"')
    if current['department_id'] != data['department_id']:
        cursor.execute('SELECT name FROM dbo.auth_group WHERE id = %s', [data['department_id']])
        changed.append(f'Phòng ban: "{current["department_name"] or "chưa có"}" → "{cursor.fetchone()[0]}"')
    if changed:
        cursor.execute(
            'UPDATE dbo.ZnsTemplates SET Name = %s, ZnsCode = %s, Owner = %s, Content = %s, DepartmentId = %s, UpdatedBy = %s, UpdatedAt = SYSUTCDATETIME() WHERE Id = %s',
            [data['name'], data['zns_code'], data['owner'], data['content'], data['department_id'], user, template_id],
        )
        _log(cursor, template_id, 'UPDATE_TEMPLATE', '; '.join(changed), user)
    existing = {v['id']: v for v in current['variables']}
    by_name = {v['name']: v for v in current['variables']}
    submitted_ids = set()
    touched = bool(changed)
    for v in data['variables']:
        old = existing.get(v['id']) if v['id'] else by_name.get(v['name'])
        if old is None:
            if v['name'] in by_name:
                raise MessagingError(f'Biến "{v["name"]}" đã tồn tại.')
            _insert_variable(cursor, template_id, v)
            _log(cursor, template_id, 'ADD_VARIABLE', f'Thêm biến: {_describe(v)}', user, v['name'])
            touched = True
            continue
        submitted_ids.add(old['id'])
        if old['name'] != v['name']:
            raise MessagingError(f'Không đổi tên biến "{old["name"]}" được. Hãy xóa biến và thêm biến mới.')
        notes = []
        if old['source'] != v['source']:
            notes.append('theo khách hàng' if v['source'] == 'customer' else 'bỏ theo khách hàng')
        if (old['default_value'] or None) != v['default_value']:
            notes.append(f'dữ liệu "{old["default_value"] or ""}" → "{v["default_value"] or ""}"')
        if (old['label'] or None) != v['label']:
            notes.append(f'nhãn "{old["label"] or ""}" → "{v["label"] or ""}"')
        if old['is_active'] != v['is_active']:
            notes.append('dùng lại' if v['is_active'] else 'ngừng dùng (giữ dữ liệu đã gửi)')
        moved = old['sort_order'] != v['sort_order']
        # Định dạng, bắt buộc do hệ thống tự tính: cập nhật nhưng không tính là sửa mẫu để không phải duyệt lại.
        derived = any(old[k] != v[k] for k in ('data_type', 'is_required'))
        if notes or moved or derived:
            cursor.execute(
                """
                UPDATE dbo.ZnsTemplateVariables SET Label = %s, DataType = %s, Source = %s, IsRequired = %s, DefaultValue = %s,
                       IsActive = %s, SortOrder = %s, UpdatedAt = SYSUTCDATETIME() WHERE Id = %s
                """,
                [v['label'], v['data_type'], v['source'], v['is_required'], v['default_value'], v['is_active'], v['sort_order'], old['id']],
            )
            touched = touched or bool(notes) or moved
        if notes:
            action = 'DISABLE_VARIABLE' if not v['is_active'] and old['is_active'] else 'UPDATE_VARIABLE'
            _log(cursor, template_id, action, '; '.join(notes), user, old['name'])
    for old in current['variables']:
        if old['id'] in submitted_ids:
            continue
        cursor.execute('DELETE FROM dbo.ZnsTemplateVariables WHERE Id = %s', [old['id']])
        _log(cursor, template_id, 'DELETE_VARIABLE', 'Xóa biến (tin đã gửi không bị ảnh hưởng)', user, old['name'])
        touched = True
    if touched:
        cursor.execute(
            """
            UPDATE dbo.ZnsTemplates SET UpdatedBy = %s, UpdatedAt = SYSUTCDATETIME(), ApprovalStatus = 'pending', SubmittedBy = %s,
                   ApprovedBy = NULL, ApprovedAt = NULL, RejectedBy = NULL, RejectedAt = NULL, RejectReason = NULL
            WHERE Id = %s
            """,
            [user, user, template_id],
        )
        audit.log('template.update', user, 'template', data['zns_code'], f'{"; ".join(changed) or "Sửa biến"} · chờ duyệt lại', data['department_id'])


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
        cursor.execute('SELECT ApprovalStatus, ZnsCode, DepartmentId FROM dbo.ZnsTemplates WHERE Id = %s AND DeletedAt IS NULL', [template_id])
        row = cursor.fetchone()
        if not row:
            raise MessagingError('Không tìm thấy mẫu tin.')
        if active and row[0] == 'rejected':
            raise MessagingError('Mẫu đã bị từ chối, hãy sửa và chờ duyệt lại trước khi bật hoạt động.')
        cursor.execute(
            'UPDATE dbo.ZnsTemplates SET IsActive = %s, UpdatedBy = %s, UpdatedAt = SYSUTCDATETIME() WHERE Id = %s AND IsActive <> %s',
            [active, user, template_id, active],
        )
        if cursor.rowcount:
            _log(cursor, template_id, 'ACTIVATE' if active else 'DEACTIVATE', 'Chuyển sang Hoạt động' if active else 'Chuyển sang Ngừng hoạt động', user)
            audit.log('template.active', user, 'template', row[1], 'Bật hoạt động' if active else 'Ngừng hoạt động', row[2])


def delete_template(template_id: int, user: str) -> None:
    """Xóa mềm: ẩn khỏi giao diện, vẫn giữ trong DB. Mẫu đã có lô gửi, kể cả lô đã hủy, không xóa được để còn tra cứu."""
    with transaction.atomic(), connection.cursor() as cursor:
        # Cùng khóa với confirm: không để vừa xóa vừa có lô mới dùng mẫu này.
        cursor.execute('SELECT ZnsCode, Name, Owner, DepartmentId FROM dbo.ZnsTemplates WITH (UPDLOCK, ROWLOCK) WHERE Id = %s AND DeletedAt IS NULL', [template_id])
        row = cursor.fetchone()
        if not row:
            raise MessagingError('Không tìm thấy mẫu tin.')
        if _has_batches(cursor, template_id):
            raise MessagingError('Mẫu đã có lô gửi nên không xóa được. Hãy chuyển sang Ngừng hoạt động.')
        cursor.execute(
            'UPDATE dbo.ZnsTemplates SET DeletedAt = SYSUTCDATETIME(), DeletedBy = %s, IsActive = 0, UpdatedBy = %s, UpdatedAt = SYSUTCDATETIME() WHERE Id = %s',
            [user, user, template_id],
        )
        _log(cursor, template_id, 'DELETE_TEMPLATE', 'Xóa mẫu tin (vẫn lưu trong DB)', user)
        audit.log('template.delete', user, 'template', row[0], f'{row[1]} · {row[2]}', row[3])


def _pending_for_review(cursor: Any, template_id: int, actor: Any) -> dict[str, Any]:
    cursor.execute('SELECT ApprovalStatus, Owner, ZnsCode, DepartmentId FROM dbo.ZnsTemplates WITH (UPDLOCK, ROWLOCK) WHERE Id = %s AND DeletedAt IS NULL', [template_id])
    row = cursor.fetchone()
    if not row or not actor.in_department(row[3]):
        raise MessagingError('Không tìm thấy mẫu tin.')
    if row[0] != 'pending':
        raise MessagingError('Mẫu tin này không còn ở trạng thái "Chờ duyệt".')
    if not actor.can_approve_template(row[1], row[3]):
        raise MessagingError(f'Bạn chưa được phân quyền duyệt mẫu của chủ hàng {row[1]}.')
    return {'owner': row[1], 'zns_code': row[2], 'department': row[3]}


def approve_template(template_id: int, actor: Any) -> None:
    with transaction.atomic(), connection.cursor() as cursor:
        info = _pending_for_review(cursor, template_id, actor)
        cursor.execute(
            "UPDATE dbo.ZnsTemplates SET ApprovalStatus = 'approved', IsActive = 1, ApprovedBy = %s, ApprovedAt = SYSUTCDATETIME() WHERE Id = %s",
            [actor.username, template_id],
        )
        _log(cursor, template_id, 'APPROVE_TEMPLATE', 'Duyệt mẫu tin', actor.username)
        audit.log('template.approve', actor.username, 'template', info['zns_code'], info['owner'], info['department'])


def reject_template(template_id: int, reason: Any, actor: Any) -> None:
    reason = str(reason or '').strip()[:500]
    if not reason:
        raise MessagingError('Vui lòng nhập lý do từ chối.')
    with transaction.atomic(), connection.cursor() as cursor:
        info = _pending_for_review(cursor, template_id, actor)
        cursor.execute(
            "UPDATE dbo.ZnsTemplates SET ApprovalStatus = 'rejected', IsActive = 0, RejectedBy = %s, RejectedAt = SYSUTCDATETIME(), RejectReason = %s WHERE Id = %s",
            [actor.username, reason, template_id],
        )
        _log(cursor, template_id, 'REJECT_TEMPLATE', f'Từ chối mẫu tin: {reason}', actor.username)
        audit.log('template.reject', actor.username, 'template', info['zns_code'], reason, info['department'])
