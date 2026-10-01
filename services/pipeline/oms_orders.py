from __future__ import annotations
import datetime as dt
import json
import logging
import os
import time
from pathlib import Path
from typing import Any
import requests
logger = logging.getLogger(__name__)
OMS_TOKEN_URL = os.environ.get('OMS_TOKEN_URL', 'https://auth-be.smartlogvn.com/connect/token')
OMS_ORDERS_URL = os.environ.get('OMS_ORDERS_URL', 'https://som-api.smartlogvn.com/api/orders/report-v2')
OMS_CLIENT_ID = os.environ.get('OMS_CLIENT_ID', 'OMS_App')
OMS_PAGE_SIZE = int(os.environ.get('OMS_PAGE_SIZE', '1000'))
TOKEN_STORE_PATH = Path(__file__).resolve().parent / 'data' / '.oms_token.json'
TARGET_SCHEMA = 'dbo'
TARGET_TABLE = 'OMS_ORDERS'
LOG_TABLE = 'OMS_ORDERS_Load_Log'
PENDING_TABLE = 'OMS_ORDERS_Pending'
VN_UTC_OFFSET = dt.timedelta(hours=7)
VN_TZ = dt.timezone(VN_UTC_OFFSET)
TERMINAL_STATUSES = {'Delivered', 'Cancelled', 'Refunded', 'RefundRejected'}

def _get_stored_refresh_token() -> str | None:
    try:
        data = json.loads(TOKEN_STORE_PATH.read_text(encoding='utf-8'))
        return data.get('refresh_token')
    except (FileNotFoundError, json.JSONDecodeError):
        return os.environ.get('OMS_REFRESH_TOKEN')

def _save_refresh_token(refresh_token: str) -> None:
    TOKEN_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_STORE_PATH.write_text(json.dumps({'refresh_token': refresh_token, 'updated_at': dt.datetime.utcnow().isoformat() + 'Z'}, indent=2), encoding='utf-8')

def _login_oms() -> str:
    refresh_token = _get_stored_refresh_token()
    if not refresh_token:
        raise RuntimeError('Chua co OMS_REFRESH_TOKEN - can dang nhap thu cong 1 lan qua trinh duyet de lay refresh_token ban dau (xem OMS_REFRESH_TOKEN trong .env).')
    response = requests.post(OMS_TOKEN_URL, data={'grant_type': 'refresh_token', 'refresh_token': refresh_token, 'client_id': OMS_CLIENT_ID}, headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if payload.get('refresh_token'):
        _save_refresh_token(payload['refresh_token'])
    return payload['access_token']

def _vn_to_oms_iso(local_dt: dt.datetime) -> str:
    utc_dt = local_dt - VN_UTC_OFFSET
    return utc_dt.strftime('%Y-%m-%dT%H:%M:%S.') + f'{utc_dt.microsecond // 1000:03d}Z'

def _oms_iso_to_vn_date(iso_str: str) -> str:
    parsed = dt.datetime.fromisoformat(iso_str)
    return parsed.astimezone(VN_TZ).strftime('%Y-%m-%d')

def _build_filter(from_iso: str, to_iso: str) -> list[dict[str, str]]:
    return [{'k': 'created_date', 'c': '>=', 'v': from_iso}, {'k': 'created_date', 'c': '<=', 'v': to_iso}]

def _fetch_page(access_token: str, page_index: int, page_size: int, filter_list: list[dict]) -> Any:
    response = requests.get(OMS_ORDERS_URL, params={'page_index': page_index, 'page_size': page_size, 'sort': '[]', 'filter': json.dumps(filter_list)}, headers={'Authorization': f'Bearer {access_token}'}, timeout=60)
    response.raise_for_status()
    return response.json()

def _fetch_all_orders(access_token: str, from_iso: str, to_iso: str) -> list[dict]:
    filter_list = _build_filter(from_iso, to_iso)
    page_index = 1
    all_rows: list[dict] = []
    while True:
        data = _fetch_page(access_token, page_index, OMS_PAGE_SIZE, filter_list)
        rows = data.get('data')
        if not isinstance(rows, list):
            raise RuntimeError(f"OMS response khong co mang 'data' nhu ky vong: {json.dumps(data)[:500]}")
        all_rows.extend(rows)
        total = data.get('total_count')
        logger.info('OMS trang %d: %d dong (tong da lay %d%s)', page_index, len(rows), len(all_rows), f'/{total}' if total is not None else '')
        if len(rows) < OMS_PAGE_SIZE:
            break
        page_index += 1
        time.sleep(0.3)
    return all_rows

def _coerce_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value

def _delete_window(target_conn: Any, from_iso: str, to_iso: str) -> None:
    cursor = target_conn.cursor()
    cursor.execute(f'DELETE FROM {TARGET_SCHEMA}.{TARGET_TABLE} WHERE created_date >= %s AND created_date <= %s', (from_iso, to_iso))

def _assert_table_exists(target_conn: Any) -> None:
    cursor = target_conn.cursor()
    cursor.execute("SELECT OBJECT_ID(%s, 'U')", (f'{TARGET_SCHEMA}.{TARGET_TABLE}',))
    if cursor.fetchone()[0] is None:
        raise RuntimeError(f'Bang {TARGET_SCHEMA}.{TARGET_TABLE} chua ton tai - tao bang truoc (xem danh sach field tra ve tu OMS de xac dinh cot).')

def _insert_rows(target_conn: Any, rows: list[dict]) -> None:
    if not rows:
        return
    columns: list[str] = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    quoted_cols = ', '.join((f'[{c}]' for c in columns))
    placeholders = ', '.join(('%s' for _ in columns))
    insert_sql = f'INSERT INTO {TARGET_SCHEMA}.{TARGET_TABLE} ({quoted_cols}) VALUES ({placeholders})'
    values = [tuple((_coerce_value(row.get(c)) for c in columns)) for row in rows]
    cursor = target_conn.cursor()
    if hasattr(cursor, 'fast_executemany'):
        cursor.fast_executemany = True
    cursor.executemany(insert_sql, values)

def _sync_window(target_conn: Any, access_token: str, from_iso: str, to_iso: str) -> list[dict]:
    rows = _fetch_all_orders(access_token, from_iso, to_iso)
    _delete_window(target_conn, from_iso, to_iso)
    _insert_rows(target_conn, rows)
    return rows

def _get_pending_dates(target_conn: Any, before_date: str) -> list[str]:
    cursor = target_conn.cursor()
    cursor.execute(f'SELECT DISTINCT created_date FROM {TARGET_SCHEMA}.{PENDING_TABLE} WHERE created_date < %s ORDER BY created_date', (before_date,))
    result = []
    for d, in cursor.fetchall():
        result.append(d.isoformat() if hasattr(d, 'isoformat') else str(d)[:10])
    return result

def _sync_pending_table(target_conn: Any, rows: list[dict]) -> None:
    if not rows:
        return
    pending_days: dict[str, str] = {}
    terminal_order_numbers: set[str] = set()
    for row in rows:
        order_number = row.get('order_number')
        if not order_number:
            continue
        status = row.get('status')
        if status in TERMINAL_STATUSES:
            terminal_order_numbers.add(order_number)
        else:
            created_date = row.get('created_date')
            if created_date:
                pending_days[order_number] = _oms_iso_to_vn_date(created_date)
    terminal_order_numbers -= pending_days.keys()
    cursor = target_conn.cursor()
    if terminal_order_numbers:
        terminal_list = sorted(terminal_order_numbers)
        placeholders = ', '.join(('%s' for _ in terminal_list))
        cursor.execute(f'DELETE FROM {TARGET_SCHEMA}.{PENDING_TABLE} WHERE order_number IN ({placeholders})', tuple(terminal_list))
    for order_number, created_date in pending_days.items():
        cursor.execute(f'\n            IF NOT EXISTS (SELECT 1 FROM {TARGET_SCHEMA}.{PENDING_TABLE} WHERE order_number = %s)\n                INSERT INTO {TARGET_SCHEMA}.{PENDING_TABLE} (order_number, created_date, FirstSeenAt)\n                VALUES (%s, %s, SYSUTCDATETIME())\n            ', (order_number, order_number, created_date))

def _log_run(target_conn: Any, start_at: str, end_at: str, row_count: int, status: str) -> None:
    cursor = target_conn.cursor()
    cursor.execute(f'\n        INSERT INTO {TARGET_SCHEMA}.{LOG_TABLE} (start_at, end_at, row_count, status, loaded_at)\n        VALUES (%s, %s, %s, %s, SYSUTCDATETIME())\n        ', (start_at, end_at, row_count, status))

def sync_oms_orders(target_conn: Any, *, start_at: str, end_at: str, **_ignored: Any) -> int:
    _assert_table_exists(target_conn)
    access_token = _login_oms()
    from_iso = _vn_to_oms_iso(dt.datetime.strptime(start_at, '%Y-%m-%d %H:%M:%S'))
    to_iso = _vn_to_oms_iso(dt.datetime.strptime(end_at, '%Y-%m-%d %H:%M:%S'))
    total = 0
    try:
        rows = _sync_window(target_conn, access_token, from_iso, to_iso)
        target_conn.commit()
        _log_run(target_conn, start_at, end_at, len(rows), 'SUCCESS')
        target_conn.commit()
        total += len(rows)
        _sync_pending_table(target_conn, rows)
        target_conn.commit()
        window_start_date = start_at[:10]
        pending_dates = _get_pending_dates(target_conn, window_start_date)
        for day in pending_dates:
            day_start = dt.datetime.strptime(day, '%Y-%m-%d')
            day_end = day_start + dt.timedelta(hours=23, minutes=59, seconds=59, microseconds=999000)
            day_from_iso = _vn_to_oms_iso(day_start)
            day_to_iso = _vn_to_oms_iso(day_end)
            day_rows = _sync_window(target_conn, access_token, day_from_iso, day_to_iso)
            target_conn.commit()
            _log_run(target_conn, day, day, len(day_rows), 'SUCCESS')
            target_conn.commit()
            total += len(day_rows)
            _sync_pending_table(target_conn, day_rows)
            target_conn.commit()
    except Exception:
        target_conn.rollback()
        _log_run(target_conn, start_at, end_at, 0, 'FAILED')
        target_conn.commit()
        raise
    logger.info('Da dong bo %d dong vao %s.%s cho window %s -> %s', total, TARGET_SCHEMA, TARGET_TABLE, start_at, end_at)
    return total
