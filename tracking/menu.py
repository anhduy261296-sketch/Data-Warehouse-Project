from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MenuItem:
    label: str
    url_name: str
    hidden: bool = False


@dataclass(frozen=True)
class MenuGroup:
    key: str
    label: str
    icon: str
    collapse_id: str
    items: tuple[MenuItem, ...]


MENU: tuple[MenuGroup, ...] = (
    MenuGroup(
        'data_tracking',
        'Data Tracking',
        'fa-table',
        'collapseDataTracking',
        (
            MenuItem('Đơn hàng E-com', 'recon-ecom'),
            MenuItem('Đơn hàng DMS duyệt', 'recon-dms-duyet'),
            MenuItem('Đơn hàng DMS xuất kho', 'recon-dms-xuatkho'),
            MenuItem('Đơn hàng WRT', 'recon-wrt'),
            MenuItem('Tồn kho SAP-WMS', 'recon-inventory'),
        ),
    ),
    MenuGroup(
        'order_detail',
        'Chi tiết đơn hàng',
        'fa-list-alt',
        'collapseOrderDetail',
        (
            MenuItem('E-com', 'detail-ecom'),
            MenuItem('DMS duyệt', 'detail-dms-duyet'),
            MenuItem('DMS xuất kho', 'detail-dms-xuatkho'),
            MenuItem('WRT', 'detail-wrt'),
        ),
    ),
    MenuGroup(
        'reports',
        'Báo cáo',
        'fa-chart-bar',
        'collapseReports',
        (
            MenuItem('ĐH theo NV - DMS', 'detail-employee-dms', hidden=True),
            MenuItem('ĐH theo NV - OMS/WMS', 'detail-employee-oms', hidden=True),
            MenuItem('Tồn kho', 'report-inventory'),
            MenuItem('E-commerce', 'report-ecom'),
        ),
    ),
)

HOME_URL_NAME = 'recon-ecom'
