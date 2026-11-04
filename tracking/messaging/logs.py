"""Nhật ký chiến dịch: thao tác trên mẫu tin và lô gửi, xem theo phòng ban."""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.db import connection

from ..core.audit import ACTION_LABELS, CAMPAIGN_SQL
from ..core.sql import rows
from .values import iso_utc

VN_OFFSET = dt.timedelta(hours=7)
_TARGET_LABELS = {'batch': 'Lô #{}', 'template': 'Mẫu {}'}


def _utc_start(value: Any, days: int = 0) -> dt.datetime | None:
    """Đầu ngày theo giờ Việt Nam, đổi sang UTC như cột CreatedAt. Ngày sai định dạng thì bỏ qua."""
    try:
        day = dt.date.fromisoformat(str(value))
    except ValueError:
        return None
    return dt.datetime.combine(day + dt.timedelta(days=days), dt.time()) - VN_OFFSET


def _where(params: Any, actor: Any) -> tuple[str, list[Any]]:
    clauses, args = [CAMPAIGN_SQL], []
    if not actor.all_departments:
        # Phòng khác không thấy log của nhau; ai cũng thấy thao tác của chính mình (vd. upload, xuất lịch sử).
        mine = f"a.DepartmentId IN ({', '.join(['%s'] * len(actor.departments))}) OR " if actor.departments else ''
        clauses.append(f'({mine}a.Actor = %s)')
        args += [*actor.departments, actor.username]
    start = _utc_start(params.get('date_from'))
    if start:
        clauses.append('a.CreatedAt >= %s')
        args.append(start)
    end = _utc_start(params.get('date_to'), days=1)
    if end:
        clauses.append('a.CreatedAt < %s')
        args.append(end)
    department = params.get('department')
    if department:
        # TRY_CONVERT: giá trị không phải số thì không khớp dòng nào thay vì lỗi SQL.
        clauses.append('a.DepartmentId = TRY_CONVERT(int, %s)')
        args.append(department)
    who =str(params.get('actor') or '').strip()
    if who:
        clauses.append('CHARINDEX(%s, a.Actor) > 0')
        args.append(who)
    query = str(params.get('q') or '').strip()
    if query:
        clauses.append('(CHARINDEX(%s, a.TargetId) > 0 OR CHARINDEX(%s, a.Detail) > 0)')
        args += [query, query]
    return ' AND '.join(clauses), args


def list_logs(params: Any, actor: Any, start: int, length: int) -> tuple[int, list[dict[str, Any]]]:
    where, args = _where(params, actor)
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM dbo.AppAuditLog a WHERE {where}', args)
        total = cursor.fetchone()[0]
        cursor.execute(
            f"""
            SELECT a.Id AS id, a.Action AS action, a.Actor AS actor, a.TargetType AS target_type, a.TargetId AS target_id,
                   a.Detail AS detail, a.IpAddress AS ip_address, a.CreatedAt AS created_at, g.name AS department_name
            FROM dbo.AppAuditLog a LEFT JOIN dbo.auth_group g ON g.id = a.DepartmentId
            WHERE {where}
            ORDER BY a.Id DESC
            OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
            """,
            [*args, start, length],
        )
        data = rows(cursor)
    for r in data:
        r['action_label'] = ACTION_LABELS.get(r['action'], r['action'])
        r['created_at'] = iso_utc(r['created_at'])
        r['target_label'] = _TARGET_LABELS[r['target_type']].format(r['target_id']) if r['target_type'] in _TARGET_LABELS and r['target_id'] else None
    return total, data
