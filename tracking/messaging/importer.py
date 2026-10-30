from __future__ import annotations

import re
import unicodedata
from typing import Any

from . import schema
from .sending import _FIXED_KEY_HEADERS, _FIXED_VALUE_HEADERS, TEMPLATE_CODE_KEY, open_workbook, sheet_rows
from .values import OWNERS, PHONE_KEYS, PLACEHOLDER_RE, MessagingError, coerce, display, normalize_key

CONTENT_KEYS = frozenset({'noidung', 'noidungtinnhan', 'content', 'message'})
NAME_KEYS = frozenset({'tenmau', 'tenmautin', 'tentemplate', 'templatename'})
SKIP_CUSTOMER_KEYS = frozenset({'stt', 'trangthaigui', 'trangthai', 'status', 'ketqua', 'ghichu'})
CUSTOMER_NAME_KEYS = frozenset({'tenkhachhang', 'hoten', 'ten', 'khachhang', 'customername'})
INFO_KEYS = {
    'zns_code': frozenset({'ma', 'mamau', 'matemplate', 'templatecode', 'mazns'}),
    'name': frozenset({'ten', 'tenmau', 'tenmautin', 'tentemplate', 'templatename'}),
    'owner': frozenset({'chuhang', 'owner'}),
    'content': frozenset({'noidung', 'noidungtinnhan', 'content', 'message'}),
}
VAR_NAME_HEADERS = frozenset({'tenbien', 'bien', 'variable'})
VAR_HEADERS = {
    'data_type': frozenset({'kieudulieu', 'kieu', 'datatype', 'type'}),
    'default_value': frozenset({'dulieu', 'giatri', 'value'}),
    'is_required': frozenset({'batbuoc', 'required'}),
    'per_customer': frozenset({'theokh', 'theokhachhang', 'percustomer'}),
}
TYPE_ALIASES = {
    'text': 'text', 'chu': 'text', 'vanban': 'text',
    'number': 'number', 'so': 'number',
    'date': 'date', 'ngay': 'date',
    'datetime': 'datetime', 'ngaygio': 'datetime', 'dateandtime': 'datetime', 'datetime24h': 'datetime',
}
YES_VALUES = frozenset({'co', 'x', 'yes', 'y', 'true', '1', 'v'})
TITLE_PREFIX_RE = re.compile(r'^\s*cấu hình gửi\s+', re.IGNORECASE)
TIME_RE = re.compile(r'\d{1,2}:\d{2}')
CONTENT_MIN_LEN = 20


def to_var_name(text: Any) -> str:
    s = unicodedata.normalize('NFD', str(text or '')).replace('đ', 'd').replace('Đ', 'd')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    s = re.sub(r'[^a-z0-9]+', '_', s).strip('_')
    if s and not s[0].isalpha():
        s = f'v_{s}'
    return s[:50]


def _guess(value: Any) -> tuple[str, str | None]:
    if value is None or str(value).strip() == '':
        return 'text', None
    text = str(value)
    if TIME_RE.search(text):
        parsed, error = coerce('datetime', value)
        if not error and parsed is not None:
            return 'datetime', display('datetime', parsed)
    parsed, error = coerce('date', value)
    if not error and parsed is not None and not TIME_RE.search(text):
        return 'date', display('date', parsed)
    return 'text', text.strip()


def _yes(value: Any) -> bool:
    return normalize_key(value) in YES_VALUES or str(value or '').strip() in {'✓', '✔'}


def _typed(data_type: str | None, value: Any) -> tuple[str, str | None]:
    if data_type is None:
        return _guess(value)
    parsed, error = coerce(data_type, value)
    if error or parsed is None:
        return data_type, None if value is None else str(value).strip() or None
    return data_type, display(data_type, parsed)


def _info_block(rows: list[tuple[int, list[Any]]], result: dict[str, Any]) -> None:
    for _, cells in rows:
        filled = [c for c in cells if c is not None and str(c).strip() != '']
        if len(filled) < 2:
            continue
        key = normalize_key(filled[0])
        for field, keys in INFO_KEYS.items():
            if key in keys and not result[field]:
                value = str(filled[1]).strip()
                if field == 'owner':
                    value = value.upper() if value.upper() in OWNERS else None
                result[field] = value or None


def _variable_table(rows: list[tuple[int, list[Any]]]) -> list[dict[str, Any]] | None:
    """Bảng theo form "Danh sách biến": Tên biến | Kiểu dữ liệu | Dữ liệu | Bắt buộc | Theo KH."""
    for pos, (_, cells) in enumerate(rows):
        keys = [normalize_key(c) for c in cells]
        name_col = next((i for i, k in enumerate(keys) if k in VAR_NAME_HEADERS), None)
        type_col = next((i for i, k in enumerate(keys) if k in VAR_HEADERS['data_type']), None)
        if name_col is None or type_col is None:
            continue
        cols = {field: next((i for i, k in enumerate(keys) if k in aliases), None) for field, aliases in VAR_HEADERS.items()}
        get = lambda row, field: row[cols[field]] if cols[field] is not None and cols[field] < len(row) else None  # noqa: E731
        variables, last_row = [], rows[pos][0]
        for row_no, row in rows[pos + 1 :]:
            raw_name = row[name_col] if name_col < len(row) else None
            if raw_name is None or str(raw_name).strip() == '' or row_no != last_row + 1:
                break
            last_row = row_no
            per_customer = _yes(get(row, 'per_customer'))
            data_type = TYPE_ALIASES.get(normalize_key(get(row, 'data_type')))
            data_type, data = _typed(data_type, None if per_customer else get(row, 'default_value'))
            variables.append({
                'name': to_var_name(raw_name),
                'data_type': data_type,
                'source': 'customer' if per_customer else 'fixed',
                'default_value': data,
                'is_required': _yes(get(row, 'is_required')) if cols['is_required'] is not None else None,
                'label': str(raw_name).strip(),
            })
        return variables
    return None


def _config_block(rows: list[tuple[int, list[Any]]]) -> tuple[list[tuple[str, Any]], set[int]]:
    for pos, (_, cells) in enumerate(rows):
        keys = [normalize_key(c) for c in cells]
        key_col = next((i for i, k in enumerate(keys) if k in _FIXED_KEY_HEADERS), None)
        if key_col is None:
            continue
        value_col = next((i for i in range(key_col + 1, len(keys)) if keys[i] in _FIXED_VALUE_HEADERS), None)
        if value_col is None:
            continue
        items, used = [], {rows[pos][0]}
        last_row = rows[pos][0]
        for row_no, row in rows[pos + 1 :]:
            name = row[key_col] if key_col < len(row) else None
            if name is None or row_no != last_row + 1 or any(normalize_key(c) in PHONE_KEYS for c in row):
                break
            last_row = row_no
            items.append((str(name).strip(), row[value_col] if value_col < len(row) else None))
            used.add(row_no)
        return items, used
    return [], set()


def _customer_headers(rows: list[tuple[int, list[Any]]], skip: set[int]) -> list[str]:
    for row_no, cells in rows[:40]:
        if row_no in skip:
            continue
        if any(normalize_key(c) in PHONE_KEYS for c in cells):
            return [str(c).strip() for c in cells if c is not None and normalize_key(c) not in PHONE_KEYS and normalize_key(c) not in SKIP_CUSTOMER_KEYS]
    return []


def parse_template_workbook(upload: Any) -> dict[str, Any]:
    wb = open_workbook(upload)
    result: dict[str, Any] = {'zns_code': None, 'name': None, 'owner': None, 'content': None, 'variables': []}
    seen: set[str] = set()

    def add(variable: dict[str, Any]) -> None:
        if variable['name'] and not schema.validate_name(variable['name']) and variable['name'] not in seen:
            seen.add(variable['name'])
            result['variables'].append(variable)

    try:
        for ws in wb.worksheets:
            rows = sheet_rows(ws)
            _info_block(rows, result)
            for _, cells in rows[:5]:
                for cell in cells:
                    if isinstance(cell, str) and not result['name'] and 'cấu hình' in cell.lower():
                        result['name'] = TITLE_PREFIX_RE.sub('', cell).strip() or None
                        result['owner'] = result['owner'] or next((o for o in OWNERS if re.search(rf'\b{o}\b', cell, re.IGNORECASE)), None)
            for _, cells in rows:
                for cell in cells:
                    if isinstance(cell, str) and not result['content'] and len(cell) >= CONTENT_MIN_LEN and PLACEHOLDER_RE.search(cell):
                        result['content'] = cell.strip()
            variables = _variable_table(rows)
            if variables is not None:
                for variable in variables:
                    add(variable)
                continue
            items, used = _config_block(rows)
            for raw_name, value in items:
                key = normalize_key(raw_name)
                if key == TEMPLATE_CODE_KEY:
                    result['zns_code'] = None if value is None else str(value).strip()
                elif key in CONTENT_KEYS and value:
                    result['content'] = str(value).strip()
                elif key in NAME_KEYS and value:
                    result['name'] = str(value).strip()
                else:
                    data_type, data = _guess(value)
                    add({'name': to_var_name(raw_name), 'data_type': data_type, 'source': 'fixed', 'default_value': data, 'is_required': None, 'label': raw_name})
            for header in _customer_headers(rows, used):
                name = 'name' if normalize_key(header) in CUSTOMER_NAME_KEYS else to_var_name(header)
                add({'name': name, 'data_type': 'text', 'source': 'customer', 'default_value': None, 'is_required': None, 'label': header})
    finally:
        wb.close()
    if not result['variables'] and not result['zns_code'] and not result['content']:
        raise MessagingError('Không tìm thấy bảng "Tên biến | Kiểu dữ liệu | Dữ liệu" trong file. Hãy dùng File mẫu.')
    return result
