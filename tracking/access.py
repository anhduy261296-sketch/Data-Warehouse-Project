"""Danh mục quyền theo từng trang và ánh xạ route -> quyền.

Mỗi route phải thuộc ít nhất một quyền: route chưa khai báo thì mặc định bị chặn (xem middleware).
Nhóm quyền (auth_group) và việc gán quyền được quản lý ở trang Cấu hình; lệnh sync_access tạo sẵn danh mục này.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from django.db import connection

from .menu import MENU
from .messaging.values import OWNERS

APP_LABEL = 'tracking'
CONTENT_TYPE_MODEL = 'access'
OPEN_ROUTES = frozenset({'home', 'no-access', 'login', 'logout', 'login-captcha', 'password-change'})


@dataclass(frozen=True)
class Perm:
    codename: str
    label: str
    routes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AccessPage:
    key: str
    label: str
    perms: tuple[Perm, ...]


@dataclass(frozen=True)
class AccessGroup:
    label: str
    pages: tuple[AccessPage, ...]


def _table_page(key: str, label: str, route: str, view: tuple[str, ...] = (), export: tuple[str, ...] = ()) -> AccessPage:
    return AccessPage(
        key,
        label,
        (Perm(f'view_{key}', 'Xem', (route, f'{route}-report', *view)), Perm(f'export_{key}', 'Xuất Excel', (f'{route}-export', *export))),
    )


CATALOG: tuple[AccessGroup, ...] = (
    AccessGroup(
        'Data Tracking',
        (
            _table_page('recon_ecom', 'Đơn hàng E-com', 'recon-ecom'),
            _table_page('recon_dms_duyet', 'Đơn hàng DMS duyệt', 'recon-dms-duyet'),
            _table_page('recon_dms_xuatkho', 'Đơn hàng DMS xuất kho', 'recon-dms-xuatkho'),
            _table_page('recon_wrt', 'Đơn hàng WRT', 'recon-wrt', view=('recon-wrt-so-status-options',)),
            _table_page(
                'recon_inventory',
                'Tồn kho SAP-WMS',
                'recon-inventory',
                view=('recon-inventory-meta', 'recon-inventory-detail', 'recon-inventory-diff-list'),
                export=('recon-inventory-detail-export', 'recon-inventory-diff-export'),
            ),
        ),
    ),
    AccessGroup(
        'Chi tiết đơn hàng',
        (
            _table_page('detail_ecom', 'E-com', 'detail-ecom'),
            _table_page('detail_dms_duyet', 'DMS duyệt', 'detail-dms-duyet'),
            _table_page('detail_dms_xuatkho', 'DMS xuất kho', 'detail-dms-xuatkho'),
            _table_page('detail_wrt', 'WRT', 'detail-wrt'),
        ),
    ),
    AccessGroup(
        'Báo cáo',
        (
            _table_page('detail_employee_dms', 'ĐH theo NV - DMS', 'detail-employee-dms'),
            _table_page('detail_employee_oms', 'ĐH theo NV - OMS/WMS', 'detail-employee-oms'),
            AccessPage(
                'report_inventory',
                'Tồn kho',
                (
                    Perm(
                        'view_report_inventory',
                        'Xem',
                        (
                            'report-inventory',
                            'report-inventory-meta',
                            'report-inventory-kpi',
                            'report-inventory-by-sku',
                            'report-inventory-top-sku',
                            'report-inventory-by-warehouse',
                            'report-inventory-by-location',
                            'report-inventory-by-group',
                        ),
                    ),
                    Perm('export_report_inventory', 'Xuất Excel', ('report-inventory-export', 'report-inventory-by-location-export')),
                ),
            ),
            AccessPage(
                'report_ecom',
                'E-commerce',
                (
                    Perm(
                        'view_report_ecom',
                        'Xem',
                        (
                            'report-ecom',
                            'report-ecom-meta',
                            'report-ecom-kpi',
                            'report-ecom-daily',
                            'report-ecom-by-sale',
                            'report-ecom-top-products',
                            'report-ecom-orders',
                        ),
                    ),
                    Perm('export_report_ecom', 'Xuất Excel', ('report-ecom-orders-export',)),
                    Perm('report_ecom_refresh', 'Cập nhật kênh bán', ('report-ecom-channels-refresh', 'report-ecom-channels-refresh-status')),
                ),
            ),
            AccessPage(
                'zns_reports',
                'Chiến dịch',
                (
                    Perm('zns_report_view', 'Xem', ('zns-report', 'zns-report-data')),
                    Perm('zns_report_export', 'Xuất Excel', ('zns-report-export',)),
                ),
            ),
        ),
    ),
    AccessGroup(
        'Quản lý chiến dịch',
        (
            AccessPage(
                'zns_templates',
                'Mẫu tin nhắn',
                (
                    Perm('zns_templates_view', 'Xem', ('zns-templates', 'zns-template-list', 'zns-template-detail', 'zns-template-edit', 'zns-template-sample')),
                    Perm('zns_templates_export', 'Xuất Excel', ('zns-template-export',)),
                    Perm('zns_templates_manage', 'Tạo / sửa / bật tắt', ('zns-template-new', 'zns-template-save', 'zns-template-import', 'zns-template-active')),
                    Perm('zns_templates_delete', 'Xóa mẫu chưa gửi', ('zns-template-delete',)),
                    Perm('zns_templates_approve', 'Duyệt / từ chối mẫu', ('zns-template-approve', 'zns-template-reject')),
                ),
            ),
            AccessPage(
                'zns_send',
                'Danh sách gửi tin',
                (
                    Perm(
                        'zns_send_view',
                        'Xem lô của mình',
                        ('zns-send', 'zns-template-list', 'zns-template-detail', 'zns-batch-list', 'zns-batch-detail', 'zns-batch-recipients', 'zns-recipient-attempts', 'zns-batch-cancel', 'zns-batch-skip', 'zns-batch-retry', 'zns-batch-retry-new'),
                    ),
                    Perm('zns_send_create', 'Tạo và gửi lô', ('zns-send-sample', 'zns-send-upload', 'zns-send-evaluate', 'zns-send-confirm')),
                    Perm('zns_batch_view_all', 'Xem lô của mọi người'),
                    Perm('zns_batch_retry', 'Gửi lại / bỏ qua lô của người khác'),
                    Perm('zns_batch_cancel', 'Hủy lô của người khác'),
                    Perm('zns_batch_export', 'Xuất khách của lô', ('zns-batch-export',)),
                    Perm('zns_batch_export_history', 'Xuất toàn bộ lịch sử', ('zns-batch-list-export',)),
                ),
            ),
            AccessPage(
                'zns_logs',
                'Nhật ký',
                (
                    Perm('zns_log_view', 'Xem', ('zns-logs', 'zns-log-list')),
                    Perm('zns_log_export', 'Xuất Excel', ('zns-log-export',)),
                ),
            ),
            AccessPage('zns_owner', 'Phạm vi chủ hàng', tuple(Perm(f'zns_owner_{o.lower()}', o) for o in OWNERS)),
            AccessPage('zns_department', 'Phạm vi phòng ban', (Perm('zns_department_all', 'Xem mọi phòng ban'),)),
        ),
    ),
    AccessGroup(
        'Cấu hình',
        (
            AccessPage(
                'config',
                'Phân quyền',
                (
                    Perm('config_users', 'Phân quyền theo người dùng', ('config-page', 'config-users', 'config-user-save', 'config-user-delete', 'config-user-reset-password', 'config-roles')),
                    Perm('config_roles', 'Phân quyền theo nhóm người dùng', ('config-page', 'config-roles', 'config-role-save', 'config-role-delete')),
                    Perm('config_audit', 'Xem nhật ký', ('config-page', 'config-audit')),
                ),
            ),
        ),
    ),
)

ALL_PERMS: tuple[Perm, ...] = tuple(p for group in CATALOG for page in group.pages for p in page.perms)
ALL_CODENAMES = frozenset(p.codename for p in ALL_PERMS)

ROUTE_PERMS: dict[str, tuple[str, ...]] = {}
for _perm in ALL_PERMS:
    for _route in _perm.routes:
        ROUTE_PERMS[_route] = (*ROUTE_PERMS.get(_route, ()), _perm.codename)

# Trang đang mở -> quyền xuất Excel của trang đó, để ẩn nút xuất khi không có quyền.
EXPORT_PERM_BY_ROUTE: dict[str, str] = {
    route: f'export_{page.key}'
    for group in CATALOG
    for page in group.pages
    if f'export_{page.key}' in ALL_CODENAMES
    for perm in page.perms
    if perm.codename == f'view_{page.key}'
    for route in perm.routes
}

_CODENAME = '|'.join(sorted(ALL_CODENAMES, key=len, reverse=True))
_CODENAME_LIST = re.compile(rf'\s*\b(?:{_CODENAME})\b(?:, (?:{_CODENAME})\b)*(?P<end>;\s*)?')
_DETAIL_WORDING = (
    ('Thêm: —; gỡ: —; ', ''),
    ('Thêm: ', 'Thêm thành viên: '),
    ('; gỡ: ', '; Gỡ thành viên: '),
    ('quyền thêm: ', 'Quyền riêng: '),
    ('quyền: ', 'Quyền: '),
    ('hoạt động: True', 'Hoạt động: Có'),
    ('hoạt động: False', 'Hoạt động: Không'),
)


def _perm_lines(match: re.Match[str]) -> str:
    codes = set(re.findall(r'\w+', match[0]))
    lines = [
        f'• {group.label} - {page.label}: {", ".join(p.label for p in page.perms if p.codename in codes)}'
        for group in CATALOG
        for page in group.pages
        if any(p.codename in codes for p in page.perms)
    ]
    return '\n' + '\n'.join(lines) + ('\n' if match['end'] else '')


def describe_audit_detail(detail: str | None) -> str | None:
    """Đổi mã quyền trong log thành tên quyền khi hiển thị, nên log đã ghi từ trước cũng dễ đọc."""
    if not detail:
        return detail
    # Đổi câu chữ trước khi thay mã quyền, để không đụng vào tên quyền như "Phân quyền: ...".
    for old, new in _DETAIL_WORDING:
        detail = detail.replace(old, new)
    return _CODENAME_LIST.sub(_perm_lines, detail)


ROLE_ADMIN = 'Quản trị hệ thống'
ROLE_VIEWER = 'Xem dữ liệu & báo cáo'
ROLE_TEMPLATE_ADMIN = 'ZNS - Quản trị mẫu'
ROLE_OWNER = {o: f'Chủ hàng {o}' for o in OWNERS}
_DATA_GROUPS = ('Data Tracking', 'Chi tiết đơn hàng', 'Báo cáo')
# Báo cáo chiến dịch xem theo chủ hàng và phòng ban của ZNS nên cấp riêng, không theo nhóm xem dữ liệu.
_NOT_VIEWER_PERMS = ('report_ecom_refresh', 'zns_report_view', 'zns_report_export')
_VIEWER_PERMS = tuple(
    p.codename for g in CATALOG if g.label in _DATA_GROUPS for page in g.pages for p in page.perms if p.codename not in _NOT_VIEWER_PERMS
)
_OWNER_PERMS = tuple(f'zns_owner_{o.lower()}' for o in OWNERS)
ROLE_DEPARTMENTS = ('IT', 'MKT', 'Kế toán')
ROLE_SEEDS: dict[str, tuple[str, ...]] = {
    ROLE_ADMIN: tuple(sorted(ALL_CODENAMES)),
    ROLE_VIEWER: _VIEWER_PERMS,
    'IT': (*_VIEWER_PERMS, 'report_ecom_refresh', 'config_users', 'config_roles', 'config_audit'),
    'MKT': (
        'view_report_ecom',
        'export_report_ecom',
        'view_report_inventory',
        'zns_templates_view',
        'zns_templates_export',
        'zns_templates_manage',
        'zns_send_view',
        'zns_send_create',
        'zns_batch_export',
        *_OWNER_PERMS,
    ),
    'Kế toán': _VIEWER_PERMS,
    'ZNS - Người soạn': ('zns_templates_view', 'zns_send_view', 'zns_send_create', 'zns_batch_export'),
    'ZNS - Người duyệt': (
        'zns_templates_view',
        'zns_send_view',
        'zns_batch_view_all',
        'zns_templates_approve',
        'zns_batch_retry',
        'zns_batch_cancel',
        'zns_batch_export',
        'zns_batch_export_history',
        'zns_log_view',
        'zns_log_export',
        'zns_report_view',
        'zns_report_export',
    ),
    ROLE_TEMPLATE_ADMIN: ('zns_templates_view', 'zns_templates_export', 'zns_templates_manage'),
    **{ROLE_OWNER[o]: (f'zns_owner_{o.lower()}',) for o in OWNERS},
}


def has(user: Any, codename: str) -> bool:
    return user.has_perm(f'{APP_LABEL}.{codename}')


def can_open(user: Any, route: str | None) -> bool:
    if user.is_superuser or route in OPEN_ROUTES:
        return True
    return any(has(user, codename) for codename in ROUTE_PERMS.get(route or '', ()))


def can_export_page(user: Any, route: str | None) -> bool:
    codename = EXPORT_PERM_BY_ROUTE.get(route or '')
    return codename is None or has(user, codename)


def first_allowed_route(user: Any) -> str | None:
    for group in MENU:
        for item in group.items:
            if not item.hidden and can_open(user, item.url_name):
                return item.url_name
    return None


def unmapped_routes() -> list[str]:
    from .urls import urlpatterns

    return sorted(p.name for p in urlpatterns if p.name and p.name not in ROUTE_PERMS and p.name not in OPEN_ROUTES)


def catalog_payload() -> list[dict[str, Any]]:
    return [
        {
            'label': g.label,
            'pages': [{'key': page.key, 'label': page.label, 'perms': [{'codename': p.codename, 'label': p.label} for p in page.perms]} for page in g.pages],
        }
        for g in CATALOG
    ]


@dataclass(frozen=True)
class ZnsActor:
    """Quyền gửi tin của một người dùng. Gom lại để lớp nghiệp vụ không phụ thuộc request."""

    username: str
    owners: tuple[str, ...]
    view_all: bool = False
    approve: bool = False
    retry: bool = False
    cancel: bool = False
    departments: tuple[int, ...] = ()
    all_departments: bool = False

    def in_department(self, department: int | None) -> bool:
        return self.all_departments or department in self.departments

    def owns(self, created_by: str | None, confirmed_by: str | None) -> bool:
        return self.username in (created_by, confirmed_by)

    def _in_batch_scope(self, owner: str | None, created_by: str | None, confirmed_by: str | None, department: int | None) -> bool:
        # Lô cũ chưa xác định được phòng ban: người tạo vẫn thấy lô của mình.
        in_scope = self.in_department(department) or (department is None and self.owns(created_by, confirmed_by))
        return owner in self.owners and in_scope

    def can_see(self, owner: str | None, created_by: str | None, confirmed_by: str | None, department: int | None) -> bool:
        return self._in_batch_scope(owner, created_by, confirmed_by, department) and (self.view_all or self.owns(created_by, confirmed_by))

    def can_cancel(self, owner: str | None, created_by: str | None, confirmed_by: str | None, department: int | None) -> bool:
        return self._in_batch_scope(owner, created_by, confirmed_by, department) and (self.cancel or self.owns(created_by, confirmed_by))

    def can_approve_template(self, owner: str | None, department: int | None) -> bool:
        return self.approve and owner in self.owners and self.in_department(department)

    def can_retry(self, owner: str | None, created_by: str | None, confirmed_by: str | None, department: int | None) -> bool:
        return self._in_batch_scope(owner, created_by, confirmed_by, department) and (self.retry or self.owns(created_by, confirmed_by))


def department_ids() -> set[int]:
    with connection.cursor() as cursor:
        cursor.execute('SELECT GroupId FROM dbo.AppDepartmentGroups')
        return {row[0] for row in cursor.fetchall()}


def user_department_ids(user: Any) -> tuple[int, ...]:
    return tuple(sorted(department_ids() & set(user.groups.values_list('id', flat=True))))


def department_options(user: Any) -> list[dict[str, Any]]:
    """Phòng ban người dùng được chọn khi tạo mẫu tin."""
    from django.contrib.auth.models import Group

    ids = department_ids() if has(user, 'zns_department_all') else user_department_ids(user)
    return [{'id': g.id, 'name': g.name} for g in Group.objects.filter(id__in=ids).order_by('name')]


def department_in_use(group_id: int) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT CASE WHEN EXISTS (SELECT 1 FROM dbo.ZnsTemplates WHERE DepartmentId = %s AND DeletedAt IS NULL) OR EXISTS (SELECT 1 FROM dbo.ZnsSendBatches WHERE DepartmentId = %s) THEN 1 ELSE 0 END',
            [group_id, group_id],
        )
        return bool(cursor.fetchone()[0])


def set_department(group_id: int, is_department: bool) -> None:
    with connection.cursor() as cursor:
        cursor.execute('DELETE FROM dbo.AppDepartmentGroups WHERE GroupId = %s', [group_id])
        if is_department:
            cursor.execute('INSERT INTO dbo.AppDepartmentGroups (GroupId) VALUES (%s)', [group_id])


def zns_actor(user: Any) -> ZnsActor:
    return ZnsActor(
        username=user.get_username(),
        owners=tuple(o for o in OWNERS if has(user, f'zns_owner_{o.lower()}')),
        view_all=has(user, 'zns_batch_view_all'),
        approve=has(user, 'zns_templates_approve'),
        retry=has(user, 'zns_batch_retry'),
        cancel=has(user, 'zns_batch_cancel'),
        departments=user_department_ids(user),
        all_departments=has(user, 'zns_department_all'),
    )
