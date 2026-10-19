from __future__ import annotations
from decimal import Decimal
from typing import Any


def num(value: Any) -> Any:
    return float(value) if isinstance(value, Decimal) else value


def rows(cursor: Any) -> list[dict[str, Any]]:
    cols = [d[0] for d in cursor.description]
    return [{c: num(v) for c, v in zip(cols, row)} for row in cursor.fetchall()]
