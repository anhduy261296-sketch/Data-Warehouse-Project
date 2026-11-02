from __future__ import annotations

from typing import Any

from django.db import connection

DETAIL_MAX_LEN = 2000


def log(action: str, actor: str, target_type: str | None = None, target_id: Any = None, detail: str | None = None) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            'INSERT INTO dbo.AppAuditLog (Action, Actor, TargetType, TargetId, Detail) VALUES (%s, %s, %s, %s, %s)',
            [action, actor, target_type, None if target_id is None else str(target_id), detail[:DETAIL_MAX_LEN] if detail else None],
        )
