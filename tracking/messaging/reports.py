"""Báo cáo chiến dịch: thống kê các lô đã gửi thật, theo đúng phạm vi xem lô của từng người."""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.db import connection

from ..core.sql import rows
from .logs import _utc_start
from .sending import ATTEMPT_RESULT_LABELS, _visibility

_DAY = 'CAST(DATEADD(HOUR, 7, b.ConfirmedAt) AS DATE)'
_FROM = """
    FROM dbo.ZnsSendRecipients r
    JOIN dbo.ZnsSendBatches b ON b.Id = r.BatchId
    LEFT JOIN dbo.ZnsTemplates t ON t.Id = b.TemplateId
    LEFT JOIN dbo.auth_group g ON g.id = b.DepartmentId
"""
# Dòng lỗi dữ liệu không được gửi nên không tính vào số khách.
_COUNTS = """
    COUNT(DISTINCT r.BatchId) AS batches,
    SUM(CASE WHEN r.Status <> 'invalid' THEN 1 ELSE 0 END) AS total,
    SUM(CASE WHEN r.Status = 'sent' THEN 1 ELSE 0 END) AS sent,
    SUM(CASE WHEN r.Status = 'failed' THEN 1 ELSE 0 END) AS failed,
    SUM(CASE WHEN r.Status = 'unknown' THEN 1 ELSE 0 END) AS unknown,
    SUM(CASE WHEN r.Status = 'invalid' THEN 1 ELSE 0 END) AS invalid
"""


def _where(params: Any, actor: Any) -> tuple[str, list[Any]]:
    visible, args = _visibility(actor)
    # Khách đã chuyển sang lô gửi lại chỉ tính ở lô mới, để một khách không bị đếm hai lần.
    clauses = ["b.Status <> 'draft'", "b.SendMode = 'live'", 'r.RetriedInBatchId IS NULL', visible]
    start = _utc_start(params.get('date_from'))
    if start:
        clauses.append('b.ConfirmedAt >= %s')
        args.append(start)
    end = _utc_start(params.get('date_to'), days=1)
    if end:
        clauses.append('b.ConfirmedAt < %s')
        args.append(end)
    if params.get('owner'):
        clauses.append('b.Owner = %s')
        args.append(params['owner'])
    # TRY_CONVERT: giá trị không phải số thì không khớp dòng nào thay vì lỗi SQL.
    if params.get('department'):
        clauses.append('b.DepartmentId = TRY_CONVERT(int, %s)')
        args.append(params['department'])
    if params.get('template'):
        clauses.append('b.TemplateId = TRY_CONVERT(int, %s)')
        args.append(params['template'])
    return ' AND '.join(clauses), args


def _with_rate(row: dict[str, Any]) -> dict[str, Any]:
    """Tỷ lệ Incom nhận tính trên số khách đã gọi API, không tính khách bỏ qua hoặc chưa gửi."""
    for key in ('total', 'sent', 'failed', 'unknown', 'invalid'):
        row[key] = row[key] or 0
    called = row['sent'] + row['failed'] + row['unknown']
    row['rate'] = round(row['sent'] * 100 / called, 1) if called else None
    return row


def _fill_days(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ngày không gửi vẫn có mặt với giá trị 0, để trục thời gian không bị dồn lại."""
    if not data:
        return []
    found = {r['day']: r for r in data}
    days = (data[-1]['day'] - data[0]['day']).days + 1
    filled = []
    for offset in range(days):
        day = data[0]['day'] + dt.timedelta(days=offset)
        filled.append(found.get(day) or {'day': day, 'batches': 0, 'total': 0, 'sent': 0, 'failed': 0, 'unknown': 0, 'invalid': 0})
    return filled


def campaign_report(params: Any, actor: Any) -> dict[str, Any]:
    where, args = _where(params, actor)

    def grouped(select: str, group: str, order: str = 'total DESC') -> list[dict[str, Any]]:
        cursor.execute(f'SELECT {select}, {_COUNTS} {_FROM} WHERE {where} GROUP BY {group} ORDER BY {order}', args)
        return [_with_rate(r) for r in rows(cursor)]

    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {_COUNTS}, COUNT(DISTINCT CASE WHEN r.Status <> 'invalid' THEN r.Phone END) AS phones {_FROM} WHERE {where}", args)
        summary = _with_rate(rows(cursor)[0])
        daily = [_with_rate(r) for r in _fill_days(grouped(f'{_DAY} AS day', _DAY, _DAY))]
        by_template = grouped('b.TemplateId AS id, t.ZnsCode AS zns_code, t.Name AS name, b.Owner AS owner', 'b.TemplateId, t.ZnsCode, t.Name, b.Owner')
        by_department = grouped('g.name AS name', 'g.name')
        by_user = grouped('b.ConfirmedBy AS name', 'b.ConfirmedBy')
        cursor.execute(
            f"""
            SELECT TOP 20 r.ErrorKind AS kind, LEFT(r.ErrorMessage, 200) AS message, COUNT(*) AS count, COUNT(DISTINCT r.BatchId) AS batches
            {_FROM} WHERE {where} AND r.Status IN ('failed', 'unknown')
            GROUP BY r.ErrorKind, LEFT(r.ErrorMessage, 200) ORDER BY count DESC
            """,
            args,
        )
        errors = rows(cursor)
    for r in daily:
        r['day'] = r['day'].isoformat()
    for r in by_department:
        r['name'] = r['name'] or 'Chưa có phòng ban'
    for r in errors:
        r['kind_label'] = ATTEMPT_RESULT_LABELS.get(r['kind'], r['kind'] or 'Khác')
    return {'summary': summary, 'daily': daily, 'templates': by_template, 'departments': by_department, 'users': by_user, 'errors': errors}
