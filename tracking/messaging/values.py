from __future__ import annotations

import datetime as dt
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

OWNERS = ('PGI', 'AWG')
DATA_TYPES = ('text', 'number', 'date', 'datetime')
SOURCES = ('customer', 'fixed')
TEXT_MAX_LEN = 500
NUMBER_MAX = Decimal('9999999999999999.99')
PLACEHOLDER_RE = re.compile(r'<\s*([A-Za-z][A-Za-z0-9_]*)\s*>')
PHONE_KEYS = frozenset({'sodienthoai', 'sdt', 'dienthoai', 'phone', 'mobile', 'sodt', 'phonenumber', 'didong', 'sdtkhachhang'})
_DATE_FORMATS = ('%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y', '%Y-%m-%d', '%Y/%m/%d', '%d/%m/%y')
_DATETIME_FORMATS = ('%d/%m/%Y %H:%M', '%d/%m/%Y %H:%M:%S', '%H:%M %d/%m/%Y', '%H:%M:%S %d/%m/%Y', '%Hh%M %d/%m/%Y', '%d-%m-%Y %H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S')


class MessagingError(ValueError):
    pass


def iso_utc(value: Any) -> str | None:
    return f'{value.isoformat()}Z' if value else None


def normalize_key(text: Any) -> str:
    s = unicodedata.normalize('NFD', str(text or '')).replace('đ', 'd').replace('Đ', 'd')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]', '', s.lower())


def cell_value(value: Any, number_format: str | None = None) -> Any:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and number_format and '%' in number_format:
        return f'{Decimal(str(round(value * 100, 6))).normalize():f}%'
    if isinstance(value, dt.datetime):
        return value.date().isoformat() if value.time() == dt.time() else value.isoformat(sep=' ')
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def normalize_phone(value: Any) -> str | None:
    if value is None or value == '':
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    digits = re.sub(r'\D', '', str(value))
    if digits.startswith('84') and len(digits) == 11:
        return digits
    if digits.startswith('0') and len(digits) == 10:
        return '84' + digits[1:]
    if len(digits) == 9 and not digits.startswith('0'):
        return '84' + digits
    return None


def _parse_number(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = re.sub(r'(vnđ|vnd|đ)$', '', str(value).strip().replace(' ', ''), flags=re.IGNORECASE)
    if re.fullmatch(r'-?\d{1,3}(\.\d{3})+(,\d+)?', text):
        text = text.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'-?\d{1,3}(,\d{3})+(\.\d+)?', text):
        text = text.replace(',', '')
    else:
        text = text.replace(',', '.')
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError from exc


def _parse_date(value: Any) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value).strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}[ T]', text):
        text = text[:10]
    for fmt in _DATE_FORMATS + _DATETIME_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError


def _parse_datetime(value: Any) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value.replace(microsecond=0)
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time())
    text = re.sub(r'\s+', ' ', str(value).strip())
    for fmt in _DATETIME_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return dt.datetime.combine(_parse_date(text), dt.time())


def coerce(data_type: str, value: Any) -> tuple[Any, str | None]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None
    try:
        if data_type == 'number':
            number = _parse_number(value)
            if abs(number) > NUMBER_MAX:
                return None, 'Số quá lớn'
            return number.quantize(Decimal('0.01')), None
        if data_type == 'date':
            return _parse_date(value), None
        if data_type == 'datetime':
            return _parse_datetime(value), None
    except ValueError:
        messages = {'number': 'Không phải số', 'date': 'Ngày không hợp lệ (dd/mm/yyyy)', 'datetime': 'Ngày giờ không hợp lệ (hh:mm dd/mm/yyyy)'}
        return None, messages[data_type]
    text = str(cell_value(value) if not isinstance(value, str) else value).strip()
    if len(text) > TEXT_MAX_LEN:
        return None, f'Dài quá {TEXT_MAX_LEN} ký tự'
    return text, None


def display(data_type: str, value: Any) -> str:
    if value is None:
        return ''
    if data_type == 'number':
        number = Decimal(value)
        whole = number == number.to_integral_value()
        text = f'{number:,.0f}' if whole else f'{number:,.2f}'.rstrip('0')
        return text.replace(',', '§').replace('.', ',').replace('§', '.')
    if data_type == 'date':
        return value.strftime('%d/%m/%Y')
    if data_type == 'datetime':
        return value.strftime('%H:%M %d/%m/%Y')
    return str(value)


def to_json(data_type: str, value: Any) -> Any:
    if value is None:
        return None
    if data_type == 'number':
        return float(value)
    if data_type in ('date', 'datetime'):
        return value.isoformat()
    return value


def placeholders(content: str) -> list[str]:
    seen: list[str] = []
    for match in PLACEHOLDER_RE.finditer(content or ''):
        name = match.group(1).lower()
        if name not in seen:
            seen.append(name)
    return seen


def render(content: str, values: dict[str, str]) -> str:
    def replace(match: re.Match) -> str:
        name = match.group(1).lower()
        return values.get(name, '') if name in values else match.group(0)

    return PLACEHOLDER_RE.sub(replace, content or '')
