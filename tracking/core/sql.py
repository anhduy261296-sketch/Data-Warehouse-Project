from __future__ import annotations
import logging
import time
from decimal import Decimal
from functools import wraps
from typing import Any

from django.db import Error, connection

DEADLOCK_RETRY_DELAYS = (0.2, 0.5, 1, 2)
logger = logging.getLogger(__name__)


def num(value: Any) -> Any:
    return float(value) if isinstance(value, Decimal) else value


def rows(cursor: Any) -> list[dict[str, Any]]:
    cols = [d[0] for d in cursor.description]
    return [{c: num(v) for c, v in zip(cols, row)} for row in cursor.fetchall()]


def retry_on_deadlock(fn):
    """Chạy lại khi SQL Server chọn câu lệnh này làm nạn nhân deadlock (1205). Chỉ dùng cho hàm chạy lại an toàn."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        for delay in DEADLOCK_RETRY_DELAYS:
            try:
                return fn(*args, **kwargs)
            except Error as exc:
                # Đang trong transaction ngoài thì để transaction đó rollback rồi mới chạy lại từ đầu.
                if '(1205)' not in str(exc) or connection.in_atomic_block:
                    raise
                logger.warning('Deadlock ở %s, chạy lại sau %ss', fn.__name__, delay)
                time.sleep(delay)
        return fn(*args, **kwargs)

    return wrapper
