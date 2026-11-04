from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from .. import access
from ..core import audit
from ..core.audit import ACTION_LABELS, CAMPAIGN_SQL
from ..core.sql import rows
from ..messaging.values import MessagingError, iso_utc
from .common import api_view, json_body, table_params

def _permissions(codenames: Any) -> list[Permission]:
    wanted = set(codenames or [])
    unknown = wanted - access.ALL_CODENAMES
    if unknown:
        raise MessagingError('Quyền không hợp lệ.')
    return list(Permission.objects.filter(content_type__app_label=access.APP_LABEL, codename__in=wanted))


def _own_codenames(user: Any) -> set[str]:
    return set(access.ALL_CODENAMES) if user.is_superuser else {p.split('.', 1)[1] for p in user.get_all_permissions() if p.startswith(f'{access.APP_LABEL}.')}


def _check_can_grant(actor: Any, added: set[str]) -> None:
    """Không ai cấp được quyền mà chính mình không có, nên không tự nâng quyền qua trang này."""
    if added - _own_codenames(actor):
        raise MessagingError('Bạn không thể cấp quyền mà chính mình chưa có.')


def _role_codenames(role_ids: Any) -> set[str]:
    return set(Permission.objects.filter(group__id__in=role_ids, content_type__app_label=access.APP_LABEL).values_list('codename', flat=True))


@require_GET
def page(request):
    user = request.user
    return render(
        request,
        'config/access.html',
        {
            'can_users': access.has(user, 'config_users'),
            'can_roles': access.has(user, 'config_roles'),
            'can_audit': access.has(user, 'config_audit'),
        },
    )


@require_GET
@api_view
def users(request):
    data = []
    for u in get_user_model().objects.prefetch_related('groups', 'user_permissions').order_by('username'):
        data.append(
            {
                'id': u.id,
                'username': u.username,
                'full_name': u.first_name,
                'email': u.email,
                'is_active': u.is_active,
                'is_superuser': u.is_superuser,
                'last_login': iso_utc(u.last_login.replace(tzinfo=None)) if u.last_login else None,
                'roles': [g.id for g in u.groups.all()],
                'perms': [p.codename for p in u.user_permissions.all() if p.codename in access.ALL_CODENAMES],
            }
        )
    return JsonResponse({'data': data})


def _clean_username(value: Any) -> str:
    username = str(value or '').strip()
    if not username:
        raise MessagingError('Vui lòng nhập tên đăng nhập.')
    try:
        UnicodeUsernameValidator()(username)
    except ValidationError as exc:
        raise MessagingError('Tên đăng nhập chỉ gồm chữ, số và @ . + - _') from exc
    return username


def _set_password(user: Any, password: str) -> None:
    try:
        validate_password(password, user)
    except ValidationError as exc:
        raise MessagingError(' '.join(exc.messages)) from exc
    user.set_password(password)


@require_POST
@api_view
def user_save(request):
    data = json_body(request)
    actor = request.user
    model = get_user_model()
    user_id = data.get('id')
    password = data.get('password') or ''
    is_active = bool(data.get('is_active', True))
    roles = list(Group.objects.filter(id__in=data.get('roles') or []))
    direct = _permissions(data.get('perms'))
    with transaction.atomic():
        if user_id:
            user = model.objects.select_for_update().filter(id=user_id).first()
            if not user:
                raise MessagingError('Không tìm thấy người dùng.')
            if user.is_superuser and not actor.is_superuser:
                raise MessagingError('Chỉ tài khoản toàn quyền mới sửa được tài khoản toàn quyền.')
            if user.pk == actor.pk and not is_active:
                raise MessagingError('Không thể tự khóa tài khoản của mình.')
            old_codes = _role_codenames(user.groups.values_list('id', flat=True)) | set(user.user_permissions.values_list('codename', flat=True))
        else:
            username = _clean_username(data.get('username'))
            if model.objects.filter(username__iexact=username).exists():
                raise MessagingError(f'Tên đăng nhập {username} đã tồn tại.')
            if not password:
                raise MessagingError('Vui lòng nhập mật khẩu cho người dùng mới.')
            user = model(username=username)
            old_codes = set()
        new_codes = _role_codenames([r.id for r in roles]) | {p.codename for p in direct}
        _check_can_grant(actor, new_codes - old_codes)
        user.first_name = str(data.get('full_name') or '').strip()[:150]
        user.email = str(data.get('email') or '').strip()[:254]
        user.is_active = is_active
        if password:
            _set_password(user, password)
        user.save()
        user.groups.set(roles)
        user.user_permissions.set([*direct, *user.user_permissions.exclude(content_type__app_label=access.APP_LABEL)])
        detail = f'Nhóm: {", ".join(r.name for r in roles) or "—"}; quyền thêm: {", ".join(sorted(p.codename for p in direct)) or "—"}; hoạt động: {is_active}'
        audit.log('user.update' if user_id else 'user.create', actor.get_username(), 'user', user.username, detail)
        if user_id and password:
            audit.log('user.password', actor.get_username(), 'user', user.username)
    return JsonResponse({'ok': True, 'id': user.id})


@require_GET
@api_view
def roles(request):
    departments = access.department_ids()
    data = [
        {
            'id': g.id,
            'name': g.name,
            'is_department': g.id in departments,
            'perms': [p.codename for p in g.permissions.all() if p.codename in access.ALL_CODENAMES],
            'members': [u.id for u in g.user_set.all()],
        }
        for g in Group.objects.prefetch_related('permissions', 'user_set').order_by('name')
    ]
    people = [
        {'id': u.id, 'username': u.username, 'full_name': u.first_name, 'is_active': u.is_active, 'is_superuser': u.is_superuser}
        for u in get_user_model().objects.order_by('username')
    ]
    return JsonResponse({'data': data, 'users': people, 'catalog': access.catalog_payload()})


def _set_members(actor: Any, group: Group, member_ids: Any, codes: set[str]) -> str:
    wanted = {u.pk: u for u in get_user_model().objects.filter(pk__in=member_ids)}
    current = {u.pk: u for u in group.user_set.all()}
    added = [u for pk, u in wanted.items() if pk not in current]
    removed = [u for pk, u in current.items() if pk not in wanted]
    if added:
        _check_can_grant(actor, codes)
    if not actor.is_superuser and any(u.is_superuser for u in (*added, *removed)):
        raise MessagingError('Chỉ tài khoản toàn quyền mới đổi được nhóm của tài khoản toàn quyền.')
    group.user_set.set(wanted.values())
    names = lambda people: ', '.join(sorted(u.username for u in people)) or '—'  # noqa: E731
    return f'Thêm: {names(added)}; gỡ: {names(removed)}'


@require_POST
@api_view
def role_save(request):
    data = json_body(request)
    name = str(data.get('name') or '').strip()[:150]
    if not name:
        raise MessagingError('Vui lòng nhập tên nhóm.')
    permissions = _permissions(data.get('perms'))
    role_id = data.get('id')
    with transaction.atomic():
        if Group.objects.filter(name__iexact=name).exclude(id=role_id or 0).exists():
            raise MessagingError(f'Nhóm {name} đã tồn tại.')
        group = Group.objects.filter(id=role_id).first() if role_id else Group()
        if group is None:
            raise MessagingError('Không tìm thấy nhóm.')
        old_codes = _role_codenames([group.id]) if role_id else set()
        new_codes = {p.codename for p in permissions}
        _check_can_grant(request.user, new_codes - old_codes)
        group.name = name
        group.save()
        group.permissions.set([*permissions, *group.permissions.exclude(content_type__app_label=access.APP_LABEL)])
        is_department = bool(data.get('is_department'))
        if not is_department and group.id in access.department_ids() and access.department_in_use(group.id):
            raise MessagingError('Phòng ban này đang có mẫu tin hoặc lô gửi nên không bỏ đánh dấu được.')
        access.set_department(group.id, is_department)
        detail = f'{"Phòng ban; " if is_department else ""}{", ".join(sorted(new_codes))}'
        if data.get('members') is not None:
            detail = f'{_set_members(request.user, group, data["members"], new_codes)}; quyền: {detail}'
        audit.log('role.update' if role_id else 'role.create', request.user.get_username(), 'role', name, detail)
    return JsonResponse({'ok': True, 'id': group.id})


@require_POST
@api_view
def role_delete(request, role_id: int):
    with transaction.atomic():
        group = Group.objects.filter(id=role_id).first()
        if not group:
            raise MessagingError('Không tìm thấy nhóm.')
        if group.user_set.exists():
            raise MessagingError('Nhóm đang có người dùng, hãy gỡ họ ra trước khi xóa.')
        if access.department_in_use(group.id):
            raise MessagingError('Phòng ban này đang có mẫu tin hoặc lô gửi nên không xóa được.')
        access.set_department(group.id, False)
        audit.log('role.delete', request.user.get_username(), 'role', group.name)
        group.delete()
    return JsonResponse({'ok': True})


@require_GET
@api_view
def audit_list(request):
    params = table_params(request)
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM dbo.AppAuditLog a WHERE NOT {CAMPAIGN_SQL}')
        total = cursor.fetchone()[0]
        cursor.execute(
            f"""
            SELECT a.Id AS id, a.Action AS action, a.Actor AS actor, a.TargetType AS target_type, a.TargetId AS target_id, a.Detail AS detail, a.IpAddress AS ip_address, a.CreatedAt AS created_at
            FROM dbo.AppAuditLog a WHERE NOT {CAMPAIGN_SQL} ORDER BY a.Id DESC OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
            """,
            [params['start'], params['length']],
        )
        data = rows(cursor)
    for r in data:
        r['action_label'] = ACTION_LABELS.get(r['action'], r['action'])
        r['created_at'] = iso_utc(r['created_at'])
    return JsonResponse({'draw': params['draw'], 'recordsTotal': total, 'recordsFiltered': total, 'data': data})
