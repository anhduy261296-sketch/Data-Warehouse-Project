from __future__ import annotations
import json
import logging
import os
import time
from decimal import Decimal
from typing import Any
import requests
from services.pipeline.common.constants import TARGET_SCHEMA
from services.pipeline.common.db import assert_tables_exist

logger = logging.getLogger(__name__)
SAP_API_BASE_URL = os.environ.get('SAP_API_BASE_URL', 'https://apierp.pgi.com.vn:64288').rstrip('/')
SAP_API_USERNAME = os.environ.get('SAP_API_USERNAME', '')
SAP_API_PASSWORD = os.environ.get('SAP_API_PASSWORD', '')
FULL_LOAD_START = '2025-06-01 00:00:00'
TARGET_TABLE = 'SAP_ITEMS'
LOG_TABLE = 'SAP_ITEMS_Load_Log'
MAX_SQL_PARAMS = 2000
_MAX_RETRIES = 3
_RETRY_DELAY_SEC = 5
FIELD_MAP = (
    ('ITEMCODE', 'ItemCode'),
    ('ITEMNAME', 'ItemName'),
    ('ITEMFOREIGNNAME', 'ItemForeignName'),
    ('INVNAME', 'InvName'),
    ('BARCODE', 'Barcode'),
    ('COLOR', 'Color'),
    ('ITEMGROUP1', 'ItemGroup1'),
    ('ITEMGROUP2', 'ItemGroup2'),
    ('ITEMGROUP3', 'ItemGroup3'),
    ('ITEMGROUP4', 'ItemGroup4'),
    ('BRAND', 'Brand'),
    ('MODEL', 'Model'),
    ('PROCODE', 'ProCode'),
    ('PGICODE', 'PgiCode'),
    ('ITEMSPEC', 'ItemSpec'),
    ('PRODUCER', 'Producer'),
    ('COUNTRY', 'Country'),
    ('UOMGROUP', 'UomGroup'),
    ('UOM', 'Uom'),
    ('SALEUOM', 'SaleUom'),
    ('BATCHNUMBER', 'BatchNumber'),
    ('SERIALNUMBER', 'SerialNumber'),
    ('SALTAXGROUP', 'SalTaxGroup'),
    ('WARRANTYDURATION', 'WarrantyDuration'),
    ('WARRANTYDURATION2', 'WarrantyDuration2'),
    ('ISACTIVE', 'IsActive'),
    ('INVENTORYITEM', 'InventoryItem'),
)
SIZE_COLUMNS = (
    'OutsideLength',
    'OutsideWidth',
    'OutsideHeight',
    'OutsideWeight',
    'InsideLength',
    'InsideWidth',
    'InsideHeight',
    'InsideWeight',
)
COLUMNS = (*(c for _, c in FIELD_MAP), *SIZE_COLUMNS, 'Size')


def _login() -> str:
    if not SAP_API_USERNAME or not SAP_API_PASSWORD:
        raise RuntimeError('Chua cau hinh SAP_API_USERNAME/SAP_API_PASSWORD (.env).')
    response = requests.post(f'{SAP_API_BASE_URL}/api/Token', json={'UserName': SAP_API_USERNAME, 'Password': SAP_API_PASSWORD}, timeout=60)
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError:
        payload = response.text
    if isinstance(payload, str) and payload.strip():
        return payload.strip().strip('"')
    if isinstance(payload, dict):
        # ten truong token khong co dinh (accesstoken / accessToken / access_token / token...) -> so khong phan biet hoa thuong, bo "_"
        for key, value in payload.items():
            if str(key).replace('_', '').lower() in ('accesstoken', 'token') and value:
                return str(value)
        # khong in gia tri (co the chua token) - chi in ten truong
        raise RuntimeError(f'API Token SAP khong tra ve token. Cac truong nhan duoc: {sorted(payload)}')
    raise RuntimeError(f'API Token SAP khong tra ve token (phan hoi kieu {type(payload).__name__}, rong hoac khong hop le).')


def _fetch_items(token: str, from_date: str, to_date: str) -> list[dict]:
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = requests.get(
                f'{SAP_API_BASE_URL}/api/Items',
                params={'fromdate': from_date, 'todate': to_date},
                headers={'Authorization': f'Bearer {token}'},
                timeout=300,
            )
            response.raise_for_status()
            rows = response.json()
            if not isinstance(rows, list):
                raise RuntimeError(f'API Items khong tra ve danh sach: {str(rows)[:300]}')
            return rows
        except (requests.exceptions.RequestException, ValueError) as exc:
            if attempt == _MAX_RETRIES:
                raise
            logger.warning(
                'SAP Items [%s -> %s]: %s (lan %d/%d), thu lai sau %ds.', from_date, to_date, exc, attempt, _MAX_RETRIES, _RETRY_DELAY_SEC
            )
            time.sleep(_RETRY_DELAY_SEC * attempt)
    return []


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ''):
        return None
    return Decimal(str(value))


def _size_values(sizes: Any) -> list[Decimal | None]:
    by_type = {str(s.get('TYPE', '')).upper(): s for s in sizes or [] if isinstance(s, dict)}
    values = []
    for kind in ('OUTSIDE', 'INSIDE'):
        size = by_type.get(kind, {})
        values.extend((_to_decimal(size.get(k)) for k in ('LENGTH', 'WIDTH', 'HEIGHT', 'WEIGHT')))
    return values


def _to_db_row(item: dict) -> tuple:
    sizes = item.get('SIZE') or []
    return (*(item.get(api) for api, _ in FIELD_MAP), *_size_values(sizes), json.dumps(sizes, ensure_ascii=False) if sizes else None)


def _assert_table_exists(target_conn: Any) -> None:
    assert_tables_exist(target_conn, (TARGET_TABLE, LOG_TABLE))


def _upsert(target_conn: Any, rows: list[tuple]) -> tuple[int, int]:
    cursor = target_conn.cursor()
    codes = [r[0] for r in rows]
    existing: dict[str, Any] = {}
    for i in range(0, len(codes), 1000):
        chunk = codes[i : i + 1000]
        cursor.execute(
            f"SELECT ItemCode, FirstLoadedAt FROM {TARGET_SCHEMA}.{TARGET_TABLE} WHERE ItemCode IN ({', '.join(['%s'] * len(chunk))})",
            tuple(chunk),
        )
        existing.update(dict(cursor.fetchall()))
        cursor.execute(f"DELETE FROM {TARGET_SCHEMA}.{TARGET_TABLE} WHERE ItemCode IN ({', '.join(['%s'] * len(chunk))})", tuple(chunk))
    cols = (*COLUMNS, 'FirstLoadedAt')
    col_sql = ', '.join(f'[{c}]' for c in cols)
    one = '(' + ', '.join(['%s'] * (len(cols) - 1)) + ', COALESCE(%s, SYSUTCDATETIME()))'
    per = max(1, MAX_SQL_PARAMS // len(cols))
    for i in range(0, len(rows), per):
        batch = rows[i : i + per]
        params = tuple((v for r in batch for v in (*r, existing.get(r[0]))))
        cursor.execute(f'INSERT INTO {TARGET_SCHEMA}.{TARGET_TABLE} ({col_sql}) VALUES ' + ', '.join([one] * len(batch)), params)
    updated = sum(1 for c in codes if c in existing)
    return (len(rows) - updated, updated)


def _log_run(
    target_conn: Any, from_date: str, to_date: str, row_count: int, inserted: int, updated: int, status: str, message: str | None = None
) -> None:
    cursor = target_conn.cursor()
    cursor.execute(
        f'INSERT INTO {TARGET_SCHEMA}.{LOG_TABLE} (from_date, to_date, row_count, inserted, updated, status, message) VALUES (%s, %s, %s, %s, %s, %s, %s)',
        (from_date, to_date, row_count, inserted, updated, status, (message or '')[:1000] or None),
    )


def last_success_to(target_conn: Any) -> str | None:
    """Moc den (to_date) cua lan nap SAP Items thanh cong gan nhat - DAG chay tay keo tiep tu day."""
    cursor = target_conn.cursor()
    cursor.execute(f"SELECT MAX(to_date) FROM {TARGET_SCHEMA}.{LOG_TABLE} WHERE status = 'SUCCESS'")
    value = cursor.fetchone()[0]
    return str(value)[:19] if value else None


def sync_sap_items(target_conn: Any, *, from_date: str, to_date: str, **_ignored: Any) -> int:
    _assert_table_exists(target_conn)
    try:
        items = _fetch_items(_login(), from_date, to_date)
        unique = {}
        for item in items:
            code = (item.get('ITEMCODE') or '').strip()
            if code:
                item['ITEMCODE'] = code
                unique[code] = item
        rows = [_to_db_row(item) for item in unique.values()]
        inserted, updated = _upsert(target_conn, rows) if rows else (0, 0)
        _log_run(target_conn, from_date, to_date, len(rows), inserted, updated, 'SUCCESS')
        target_conn.commit()
    except Exception as exc:
        target_conn.rollback()
        _log_run(target_conn, from_date, to_date, 0, 0, 0, 'FAILED', str(exc))
        target_conn.commit()
        raise
    logger.info('SAP Items [%s -> %s]: %d ma (moi %d, cap nhat %d)', from_date, to_date, len(rows), inserted, updated)
    return len(rows)
