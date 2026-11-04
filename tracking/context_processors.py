from __future__ import annotations

from typing import Any

from . import access
from .menu import HOME_URL_NAME, MENU


def _breadcrumbs(user: Any, current: str | None) -> list[dict[str, Any]]:
    """Lấy từ menu: Nhóm / Trang. Trang không có trong menu hoặc không có quyền (403, 404) thì không hiện."""
    if not current or not access.can_open(user, current):
        return []
    for group in MENU:
        item = next((i for i in group.items if current == i.url_name or current in i.active_for), None)
        if item:
            # Nhóm không có trang riêng: liên kết tới trang đầu tiên người này mở được.
            first = next((i.url_name for i in group.items if not i.hidden and access.can_open(user, i.url_name)), None)
            return [
                {'label': group.label, 'url_name': first if first != current else None},
                {'label': item.label, 'url_name': item.url_name if item.url_name != current else None},
            ]
    return []


def sidebar_menu(request) -> dict[str, Any]:
    match = getattr(request, 'resolver_match', None)
    current = match.url_name if match else None
    groups = []
    for group in MENU:
        items = [
            {'label': i.label, 'url_name': i.url_name, 'active': current == i.url_name or current in i.active_for}
            for i in group.items
            if not i.hidden and access.can_open(request.user, i.url_name)
        ]
        if items:
            groups.append(
                {
                    'key': group.key,
                    'label': group.label,
                    'icon': group.icon,
                    'collapse_id': group.collapse_id,
                    'items': items,
                    'active': any(i['active'] for i in items),
                }
            )
    return {'sidebar_menu': groups, 'breadcrumbs': _breadcrumbs(request.user, current), 'home_url_name': HOME_URL_NAME, 'page_can_export': access.can_export_page(request.user, current)}
