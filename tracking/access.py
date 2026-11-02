"""Danh mục quyền theo từng trang và ánh xạ route -> quyền.

Mỗi route phải thuộc ít nhất một quyền: route chưa khai báo thì mặc định bị chặn (xem middleware).
Vai trò (auth_group) và việc gán quyền được quản lý ở trang Cấu hình; lệnh sync_access tạo sẵn danh mục này.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .menu import MENU
from .messaging.values import OWNERS

APP_LABEL = 'tracking'
CONTENT_TYPE_MODEL = 'access'
OPEN_ROUTES = frozenset({'home', 'no-access', 'login', 'logout', 'login-captcha'})


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
                ),
            ),
            AccessPage(
                'zns_send',
                'Danh sách gửi tin',
                (
                    Perm(
                        'zns_send_view',
                        'Xem lô của mình',
                        ('zns-send', 'zns-template-list', 'zns-template-detail', 'zns-batch-list', 'zns-batch-detail', 'zns-batch-recipients', 'zns-recipient-attempts', 'zns-batch-cancel', 'zns-batch-skip'),
                    ),
                    Perm('zns_send_create', 'Tạo lô (upload, xác nhận chờ duyệt)', ('zns-send-sample', 'zns-send-upload', 'zns-send-evaluate', 'zns-send-confirm')),
                    Perm('zns_batch_view_all', 'Xem lô của mọi người'),
                    Perm('zns_batch_approve', 'Duyệt / từ chối lô', ('zns-batch-approve', 'zns-batch-reject')),
                    Perm('zns_batch_retry', 'Gửi lại / bỏ qua khách lỗi', ('zns-batch-retry', 'zns-batch-retry-new')),
                    Perm('zns_batch_cancel', 'Hủy lô của người khác'),
                    Perm('zns_batch_export', 'Xuất khách của lô', ('zns-batch-export',)),
                    Perm('zns_batch_export_history', 'Xuất toàn bộ lịch sử', ('zns-batch-list-export',)),
                ),
            ),
            AccessPage('zns_owner', 'Phạm vi chủ hàng', tuple(Perm(f'zns_owner_{o.lower()}', o) for o in OWNERS)),
        ),
    ),
    AccessGroup(
        'Cấu hình',
        (
            AccessPage(
                'config',
                'Phân quyền & cấu hình',
                (
                    Perm('config_users', 'Quản lý người dùng', ('config-page', 'config-users', 'config-user-save', 'config-roles')),
                    Perm('config_roles', 'Quản lý vai trò', ('config-page', 'config-roles', 'config-role-save', 'config-role-delete')),
                    Perm('config_limits', 'Hạn mức gửi tin', ('config-page', 'config-limits', 'config-limits-save')),
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

ROLE_ADMIN = 'Quản trị hệ thống'
ROLE_VIEWER = 'Xem dữ liệu & báo cáo'
ROLE_TEMPLATE_ADMIN = 'ZNS - Quản trị mẫu'
ROLE_OWNER = {o: f'Chủ hàng {o}' for o in OWNERS}
_DATA_GROUPS = ('Data Tracking', 'Chi tiết đơn hàng', 'Báo cáo')
ROLE_SEEDS: dict[str, tuple[str, ...]] = {
    ROLE_ADMIN: tuple(sorted(ALL_CODENAMES)),
    ROLE_VIEWER: tuple(
        p.codename for g in CATALOG if g.label in _DATA_GROUPS for page in g.pages for p in page.perms if p.codename != 'report_ecom_refresh'
    ),
    'ZNS - Người soạn': ('zns_templates_view', 'zns_send_view', 'zns_send_create', 'zns_batch_export'),
    'ZNS - Người duyệt': (
        'zns_templates_view',
        'zns_send_view',
        'zns_batch_view_all',
        'zns_batch_approve',
        'zns_batch_retry',
        'zns_batch_cancel',
        'zns_batch_export',
        'zns_batch_export_history',
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
    is_admin: bool = False  # tài khoản toàn quyền (superuser) được tự duyệt, tự gửi lại lô của mình

    def owns(self, created_by: str | None, confirmed_by: str | None) -> bool:
        return self.username in (created_by, confirmed_by)

    def can_see(self, owner: str | None, created_by: str | None, confirmed_by: str | None) -> bool:
        return owner in self.owners and (self.view_all or self.owns(created_by, confirmed_by))

    def can_cancel(self, owner: str | None, created_by: str | None, confirmed_by: str | None) -> bool:
        return owner in self.owners and (self.cancel or self.owns(created_by, confirmed_by))

    def can_approve(self, owner: str | None, created_by: str | None, confirmed_by: str | None) -> bool:
        return self.approve and owner in self.owners and (self.is_admin or not self.owns(created_by, confirmed_by))

    def can_skip(self, owner: str | None, created_by: str | None, confirmed_by: str | None) -> bool:
        return owner in self.owners and (self.retry or self.owns(created_by, confirmed_by))

    def can_retry(self, owner: str | None, created_by: str | None, confirmed_by: str | None) -> bool:
        return self.retry and owner in self.owners and (self.is_admin or not self.owns(created_by, confirmed_by))


def zns_actor(user: Any) -> ZnsActor:
    return ZnsActor(
        username=user.get_username(),
        owners=tuple(o for o in OWNERS if has(user, f'zns_owner_{o.lower()}')),
        view_all=has(user, 'zns_batch_view_all'),
        approve=has(user, 'zns_batch_approve'),
        retry=has(user, 'zns_batch_retry'),
        cancel=has(user, 'zns_batch_cancel'),
        is_admin=user.is_superuser,
    )
