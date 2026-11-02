from __future__ import annotations

from typing import Any

from . import access
from .menu import HOME_URL_NAME, MENU


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
    return {'sidebar_menu': groups, 'home_url_name': HOME_URL_NAME, 'page_can_export': access.can_export_page(request.user, current)}
