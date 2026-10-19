from __future__ import annotations

from typing import Any

from .menu import HOME_URL_NAME, MENU


def sidebar_menu(request) -> dict[str, Any]:
    match = getattr(request, 'resolver_match', None)
    current = match.url_name if match else None
    groups = []
    for group in MENU:
        items = [{'label': i.label, 'url_name': i.url_name, 'active': i.url_name == current} for i in group.items if not i.hidden]
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
    return {'sidebar_menu': groups, 'home_url_name': HOME_URL_NAME}
