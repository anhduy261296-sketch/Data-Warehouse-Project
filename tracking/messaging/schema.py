from __future__ import annotations

import re

NAME_RE = re.compile(r'^[a-z][a-z0-9_]{0,49}$')
SYSTEM_COLUMNS = frozenset({'id', 'batchid', 'recipientid', 'phone', 'createdat'})


def validate_name(name: str) -> str | None:
    if not NAME_RE.match(name or ''):
        return 'Tên biến chỉ gồm chữ thường không dấu, số, dấu _ và bắt đầu bằng chữ (tối đa 50 ký tự)'
    if name.replace('_', '') in SYSTEM_COLUMNS:
        return f'"{name}" là tên dành riêng của hệ thống, hãy đặt tên khác'
    return None
