"""Hạn mức gửi tin theo chủ hàng: tối đa mỗi lô và tối đa mỗi tháng (theo số tin, hoặc theo ngân sách khi đã có giá)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from .values import OWNERS, MessagingError
from . import provider

BASIS_COUNT = 'count'
BASIS_BUDGET = 'budget'
_VN_OFFSET = dt.timedelta(hours=7)


def _load(cursor: Any, owner: str, lock: bool = False) -> dict[str, Any]:
    cursor.execute(
        f"""
        SELECT MaxPerBatch, LimitBasis, MaxPerMonth, UnitPrice, MaxBudgetPerMonth
        FROM dbo.ZnsSendLimits {'WITH (UPDLOCK, ROWLOCK)' if lock else ''} WHERE Owner = %s
        """,
        [owner],
    )
    row = cursor.fetchone()
    keys = ('max_per_batch', 'basis', 'max_per_month', 'unit_price', 'max_budget')
    return dict(zip(keys, row)) if row else dict.fromkeys(keys)


def month_cap(limit: dict[str, Any]) -> int | None:
    if limit['basis'] == BASIS_BUDGET and limit['unit_price'] and limit['max_budget'] is not None:
        return int(limit['max_budget'] / limit['unit_price'])
    return limit['max_per_month']


def _month_start_utc() -> dt.datetime:
    now_vn = dt.datetime.utcnow() + _VN_OFFSET
    return now_vn.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - _VN_OFFSET


def _billed(cursor: Any, owner: str) -> int:
    """Số tin đã tính phí trong tháng. "Chưa rõ" cũng tính vì tin có thể đã đi."""
    cursor.execute(
        """
        SELECT COUNT(*) FROM dbo.ZnsSendAttempts a JOIN dbo.ZnsSendBatches b ON b.Id = a.BatchId
        WHERE b.Owner = %s AND a.CreatedAt >= %s AND a.Result IN ('sent', 'unknown')
        """,
        [owner, _month_start_utc()],
    )
    return cursor.fetchone()[0]


def _reserved(cursor: Any, owner: str) -> int:
    cursor.execute(
        """
        SELECT COUNT(*) FROM dbo.ZnsSendRecipients r JOIN dbo.ZnsSendBatches b ON b.Id = r.BatchId
        WHERE b.Owner = %s AND b.Status IN ('sending', 'paused') AND b.SendMode = 'live' AND r.Status IN ('pending', 'sending')
        """,
        [owner],
    )
    return cursor.fetchone()[0]


def check_batch(cursor: Any, owner: str, count: int) -> None:
    maximum = _load(cursor, owner)['max_per_batch']
    if maximum is not None and count > maximum:
        raise MessagingError(f'Lô có {count:,} tin, vượt hạn mức {maximum:,} tin mỗi lô của {owner}.')


def check_month(cursor: Any, owner: str, extra: int) -> None:
    """Giữ khóa hàng hạn mức tới hết transaction để 2 lần duyệt cùng lúc không cùng vượt hạn mức."""
    if provider.send_mode() != 'live':
        return
    cap = month_cap(_load(cursor, owner, lock=True))
    if cap is None:
        return
    used = _billed(cursor, owner) + _reserved(cursor, owner)
    if used + extra > cap:
        raise MessagingError(f'Vượt hạn mức tháng của {owner}: đã dùng {used:,} / {cap:,} tin, lô này cần thêm {extra:,} tin.')


def exhausted_reason(cursor: Any, owner: str) -> str | None:
    if provider.send_mode() != 'live':
        return None
    cap = month_cap(_load(cursor, owner))
    if cap is None or _billed(cursor, owner) < cap:
        return None
    return f'Lô tạm dừng do đã hết hạn mức tháng của {owner} ({cap:,} tin).'


def approval_summary(cursor: Any, owner: str, count: int) -> dict[str, Any]:
    limit = _load(cursor, owner)
    price = limit['unit_price']
    return {
        'count': count,
        'used': _billed(cursor, owner) + _reserved(cursor, owner),
        'cap': month_cap(limit),
        'max_per_batch': limit['max_per_batch'],
        'unit_price': float(price) if price is not None else None,
        'est_cost': float(price * count) if price is not None else None,
    }


def list_limits(cursor: Any) -> list[dict[str, Any]]:
    data = []
    for owner in OWNERS:
        limit = _load(cursor, owner)
        data.append(
            {
                'owner': owner,
                'max_per_batch': limit['max_per_batch'],
                'basis': limit['basis'] or BASIS_COUNT,
                'max_per_month': limit['max_per_month'],
                'unit_price': float(limit['unit_price']) if limit['unit_price'] is not None else None,
                'max_budget': float(limit['max_budget']) if limit['max_budget'] is not None else None,
                'cap': month_cap(limit) if limit['basis'] else None,
                'used': _billed(cursor, owner) + _reserved(cursor, owner),
            }
        )
    return data


def _positive_int(value: Any, label: str) -> int | None:
    if value in (None, ''):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise MessagingError(f'{label} phải là số nguyên.') from exc
    if number <= 0:
        raise MessagingError(f'{label} phải lớn hơn 0.')
    return number


def _positive_decimal(value: Any, label: str) -> Decimal | None:
    if value in (None, ''):
        return None
    try:
        number = Decimal(str(value))
    except ArithmeticError as exc:
        raise MessagingError(f'{label} phải là số.') from exc
    if not number.is_finite() or number <= 0:
        raise MessagingError(f'{label} phải lớn hơn 0.')
    return number


def save_limit(cursor: Any, data: dict[str, Any], user: str) -> None:
    owner = data.get('owner')
    if owner not in OWNERS:
        raise MessagingError('Chủ hàng không hợp lệ.')
    basis = data.get('basis') or BASIS_COUNT
    if basis not in (BASIS_COUNT, BASIS_BUDGET):
        raise MessagingError('Cách tính hạn mức không hợp lệ.')
    price = _positive_decimal(data.get('unit_price'), 'Giá mỗi tin')
    budget = _positive_decimal(data.get('max_budget'), 'Ngân sách tháng')
    if basis == BASIS_BUDGET and (price is None or budget is None):
        raise MessagingError('Tính theo ngân sách cần nhập giá mỗi tin và ngân sách tháng.')
    cursor.execute(
        """
        UPDATE dbo.ZnsSendLimits SET MaxPerBatch = %s, LimitBasis = %s, MaxPerMonth = %s, UnitPrice = %s, MaxBudgetPerMonth = %s,
               UpdatedBy = %s, UpdatedAt = SYSUTCDATETIME()
        WHERE Owner = %s
        """,
        [_positive_int(data.get('max_per_batch'), 'Tối đa mỗi lô'), basis, _positive_int(data.get('max_per_month'), 'Tối đa mỗi tháng'), price, budget, user, owner],
    )
