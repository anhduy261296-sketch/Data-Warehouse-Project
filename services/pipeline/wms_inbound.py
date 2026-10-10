from __future__ import annotations
import datetime as dt
import logging
import os
import time
from typing import Any
import requests
logger = logging.getLogger(__name__)
WMS_LOGIN_URL = os.environ.get('WMS_LOGIN_URL', 'https://authentication.smartlog.info/api/User/login')
WMS_INBOUND_URL = os.environ.get('WMS_INBOUND_URL', 'https://poms-be.smartlogix.biz/api/standardized/v1/reports/inbound')
WMS_USERNAME = os.environ.get('WMS_USERNAME', '')
WMS_PASSWORD = os.environ.get('WMS_PASSWORD', '')
WMS_STORERKEY = os.environ.get('WMS_STORERKEY', 'PGI')
WMS_INBOUND_FIELD_NAMES = ['adddate', 'receiptkey', 'storerkey', 'type', 'suppliercode', 'sku', 'status', 'externreceiptkey', 'externalreceiptkey2', 'masterreceipt', 'pokey', 'pokey2', 'fromwhseid', 'expectedreceiptdate', 'receiptdate', 'approve', 'businessunitorder', 'invorg', 'company', 'supplier_address', 'taxcode', 'buyer', 'consigneekey', 'consigneename', 'destname', 'destcode', 'shipto', 'notifypartykey', 'carriercode', 'carriername1', 'trailernumber', 'drivername', 'tripid', 'transportationmode', 'transportationservice', 'begintime', 'endtime', 'vesselcode', 'vesselname', 'gacdate', 'door', 'id_declaration', 'declarationplace', 'declarationdate', 'declarationtype', 'documenttime', 'plantcode', 'cabcode', 'division', 'billoflading', 'contract', 'containerkey', 'containertype', 'seal', 'invoice_no_sai', 'transportcharges', 'invoiceno', 'syncstatus', 'syncmess', 'syncdate', 'notes', 'notes2', 'droplist1', 'droplist2', 'droplist3', 'droplist4', 'droplist5', 'droplist6', 'droplist7', 'droplist8', 'droplist9', 'droplist10', 'susr1', 'susr2', 'susr3', 'susr4', 'susr5', 'susr6', 'susr7', 'susr8', 'susr9', 'susr10', 'susr11', 'susr12', 'susr13', 'susr14', 'susr15', 'susr16', 'susr17', 'susr18', 'skudesc', 'upccode', 'denominator', 'uom', 'toloc', 'category', 'conditioncode', 'qtyexpectedpcs', 'qtyreceivedpcs', 'qtyexpectedcs', 'qtyreceivedcs', 'qtyexpectedpl', 'qtyreceivedpl', 'percentshelflifeatreceived', 'unitprice', 'price', 'LENGTH', 'width', 'height', 'cube', 'grosswgt', 'netwgt', 'cubeexpected', 'grosswgtexpected', 'netwgtexpected', 'percentage', 'unitid', 'cartonid', 'palletid', 'lottable01', 'lottable02', 'lottable03', 'lottable04', 'lottable05', 'lottable06', 'lottable07', 'lottable08', 'lottable09', 'lottable10', 'lottable11', 'lottable12', 'datereceived', 'noteitem', 'addwho', 'editwho', 'sku_susr1', 'sku_susr2', 'sku_susr3', 'sku_susr4', 'sku_susr5', 'sku_susr6', 'sku_susr7', 'sku_susr8', 'sku_susr9', 'sku_susr10', 'masterunit', 'innerpack', 'pallet', 'qtyexpected_otherunit1', 'qtyreceived_otherunit1', 'qtyexpected_otherunit2', 'qtyreceived_otherunit2', 'stdcube', 'stdnetwgt', 'stdgrosswgt', 'skugroup', 'qtyevenexpectedcs', 'qtyoddexpectedpcs', 'qtyevenreceivedcs', 'qtyoddreceivedpcs', 'acreage', 'susr1_rd', 'susr2_rd', 'susr3_rd', 'susr4_rd', 'susr5_rd', 'packuom8', 'otherunit1', 'packuom9', 'otherunit2', 'manageimei', 'manageimeiout', 'stdlength', 'stdwidth', 'stdheigth', 'putawayzone']
TARGET_SCHEMA = 'dbo'
TARGET_TABLE = 'WMS_INBOUND'
LOG_TABLE = 'WMS_INBOUND_Load_Log'
PENDING_TABLE = 'WMS_INBOUND_Pending'
PGI_WAREHOUSE_CODES = ['WH102', 'WH103', 'WH104', 'WH105', 'WH106', 'WH107', 'WH108', 'WH109', 'WH110', 'WH111', 'WH112', 'WH113', 'WH114', 'WH116', 'WH117', 'WH118', 'WH119', 'WH998']

def _login() -> str:
    if not WMS_USERNAME or not WMS_PASSWORD:
        raise RuntimeError('Chua cau hinh WMS_USERNAME/WMS_PASSWORD (.env) - can dien truoc khi chay DAG.')
    response = requests.post(WMS_LOGIN_URL, json={'username': WMS_USERNAME, 'password': WMS_PASSWORD}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    token = payload.get('token')
    if not token:
        raise RuntimeError(f"Login WMS khong tra ve 'token': {str(payload)[:300]}")
    return token
_MAX_FETCH_RETRIES = 3
_FETCH_RETRY_DELAY_SEC = 3
_BUSY_MAX_RETRIES = 5
_BUSY_RETRY_DELAY_SEC = 20

def _is_server_busy(exc: requests.exceptions.HTTPError) -> bool:
    if exc.response is None:
        return False
    return 'server is busy' in exc.response.text.lower()

_TOKEN_CACHE: dict[str, str] = {}
_MAX_RELOGINS = 3
_RELOGIN_DELAY_SEC = 5

def _fetch_inbound_raw(token: str, whseid: str, from_date: str, to_date: str) -> tuple[list[dict], int | None]:
    busy_retries = 0
    other_retries = 0
    relogins = 0
    while True:
        try:
            return _fetch_inbound_raw_once(_TOKEN_CACHE.get('token') or token, whseid, from_date, to_date)
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 401 and relogins < _MAX_RELOGINS:
                relogins += 1
                logger.warning('WMS inbound kho %s [%s -> %s]: token bi tu choi (401) - dang nhap lai (lan %d/%d). Neu lap lai lien tuc, kiem tra co noi khac dang dang nhap cung tai khoan WMS khong.', whseid, from_date, to_date, relogins, _MAX_RELOGINS)
                time.sleep(_RELOGIN_DELAY_SEC * relogins)
                _TOKEN_CACHE['token'] = _login()
                continue
            if _is_server_busy(exc):
                busy_retries += 1
                if busy_retries > _BUSY_MAX_RETRIES:
                    raise
                logger.warning('WMS inbound kho %s [%s -> %s]: server bao busy (lan %d/%d), cho %ds roi thu lai.', whseid, from_date, to_date, busy_retries, _BUSY_MAX_RETRIES, _BUSY_RETRY_DELAY_SEC)
                time.sleep(_BUSY_RETRY_DELAY_SEC)
                continue
            other_retries += 1
            if other_retries > _MAX_FETCH_RETRIES:
                raise
            logger.warning('WMS inbound kho %s [%s -> %s]: HTTP %s (lan %d/%d), thu lai sau %ds.', whseid, from_date, to_date, status, other_retries, _MAX_FETCH_RETRIES, _FETCH_RETRY_DELAY_SEC)
            time.sleep(_FETCH_RETRY_DELAY_SEC)

def _fetch_inbound_raw_once(token: str, whseid: str, from_date: str, to_date: str) -> tuple[list[dict], int | None]:
    response = requests.post(WMS_INBOUND_URL, json={'whseid': whseid, 'storerkey': [WMS_STORERKEY], 'typeDate': 'adddate', 'fromDate': from_date, 'toDate': to_date, 'fieldNames': WMS_INBOUND_FIELD_NAMES}, headers={'token': token, 'whseid': whseid}, timeout=120)
    response.raise_for_status()
    payload = response.json()
    rows = payload.get('data')
    if not isinstance(rows, list):
        raise RuntimeError(f"WMS inbound response khong co mang 'data': {str(payload)[:500]}")
    return (rows, payload.get('total'))

def _fetch_inbound(token: str, whseid: str, from_date: str, to_date: str, _depth: int=0) -> list[dict]:
    rows, total = _fetch_inbound_raw(token, whseid, from_date, to_date)
    if total is None or total == len(rows):
        return rows
    from_dt = dt.datetime.strptime(from_date, '%Y-%m-%d %H:%M:%S')
    to_dt = dt.datetime.strptime(to_date, '%Y-%m-%d %H:%M:%S')
    window = to_dt - from_dt
    if _depth >= 10 or window <= dt.timedelta(days=1):
        logger.warning('WMS inbound kho %s [%s -> %s]: total=%s nhung chi nhan %d dong - da chia toi han (do sau %d, cua so %s) van lech, co the API gioi han theo cach khac - can hoi lai Smartlog.', whseid, from_date, to_date, total, len(rows), _depth, window)
        return rows
    mid_dt = from_dt + window / 2
    mid_date = mid_dt.strftime('%Y-%m-%d %H:%M:%S')
    logger.info('WMS inbound kho %s [%s -> %s]: total=%s != %d dong nhan duoc - chia doi cua so tai %s va goi lai.', whseid, from_date, to_date, total, len(rows), mid_date)
    first_half = _fetch_inbound(token, whseid, from_date, mid_date, _depth + 1)
    second_half = _fetch_inbound(token, whseid, mid_date, to_date, _depth + 1)
    return first_half + second_half

def _assert_table_exists(target_conn: Any) -> None:
    cursor = target_conn.cursor()
    cursor.execute("SELECT OBJECT_ID(%s, 'U')", (f'{TARGET_SCHEMA}.{TARGET_TABLE}',))
    if cursor.fetchone()[0] is None:
        raise RuntimeError(f'Bang {TARGET_SCHEMA}.{TARGET_TABLE} chua ton tai - chay DDL truoc.')
_BUSINESS_KEY = ['receiptkey', 'externreceiptkey', 'lpnid', 'sku']
_IGNORED_RESPONSE_FIELDS = {'whseid'}

def _merge_rows(target_conn: Any, whseid: str, rows: list[dict]) -> None:
    if not rows:
        return
    columns: list[str] = []
    seen = set()
    for row in rows:
        for key in row:
            if key in _IGNORED_RESPONSE_FIELDS:
                continue
            if key.lower() not in seen:
                seen.add(key.lower())
                columns.append(key)
    cursor = target_conn.cursor()
    for row in rows:
        row_ci = {k.lower(): v for k, v in row.items()}
        values = {c: row_ci.get(c.lower()) for c in columns}
        set_clause = ', '.join((f'[{c}] = %s' for c in columns))
        insert_cols = ', '.join((f'[{c}]' for c in columns))
        insert_placeholders = ', '.join(('%s' for _ in columns))
        key_values = [values.get(k) for k in _BUSINESS_KEY]
        exists_clause = ' AND '.join((f'[{k}] = %s' if key_values[i] is not None else f'[{k}] IS NULL' for i, k in enumerate(_BUSINESS_KEY)))
        match_params = [v for v in key_values if v is not None]
        column_values = [values[c] for c in columns]
        params = [*match_params, *column_values, *match_params, whseid, WMS_STORERKEY, *column_values]
        cursor.execute(f'\n            IF EXISTS (SELECT 1 FROM {TARGET_SCHEMA}.{TARGET_TABLE} WHERE {exists_clause})\n                UPDATE {TARGET_SCHEMA}.{TARGET_TABLE}\n                SET {set_clause}, _scraped_at = SYSUTCDATETIME()\n                WHERE {exists_clause}\n            ELSE\n                INSERT INTO {TARGET_SCHEMA}.{TARGET_TABLE}\n                    (_whseid, _storerkey, {insert_cols})\n                VALUES (%s, %s, {insert_placeholders})\n            ', params)

def _is_pending(row: dict) -> bool:
    datereceived = row.get('datereceived')
    syncstatus = row.get('syncstatus')
    return not datereceived or syncstatus == 'Error'

def _is_cancelled(row: dict) -> bool:
    return row.get('status') == '1'

def _row_adddate(row: dict) -> str | None:
    adddate = row.get('adddate')
    if not adddate:
        return None
    return str(adddate)[:10]

def _sync_pending_table(target_conn: Any, whseid: str, rows: list[dict]) -> None:
    if not rows:
        return
    cursor = target_conn.cursor()
    match_clause = ' AND '.join((f'[{k}] = %s' for k in _BUSINESS_KEY))
    for row in rows:
        key_values = [row.get(k) for k in _BUSINESS_KEY]
        if any((v is None for v in key_values)):
            continue
        cancelled = _is_cancelled(row)
        keep = cancelled or _is_pending(row)
        if keep:
            adddate = _row_adddate(row)
            if not adddate:
                continue
            needs_recheck = 0 if cancelled else 1
            note = 'Cancel' if cancelled else None
            insert_cols = ', '.join((f'[{k}]' for k in _BUSINESS_KEY))
            insert_placeholders = ', '.join(('%s' for _ in _BUSINESS_KEY))
            cursor.execute(f'\n                IF EXISTS (\n                    SELECT 1 FROM {TARGET_SCHEMA}.{PENDING_TABLE}\n                    WHERE whseid = %s AND {match_clause}\n                )\n                    UPDATE {TARGET_SCHEMA}.{PENDING_TABLE}\n                    SET ReCheck = %s, Note = %s\n                    WHERE whseid = %s AND {match_clause}\n                ELSE\n                    INSERT INTO {TARGET_SCHEMA}.{PENDING_TABLE}\n                        (whseid, {insert_cols}, adddate, ReCheck, Note, FirstSeenAt)\n                    VALUES (%s, {insert_placeholders}, %s, %s, %s, SYSUTCDATETIME())\n                ', [whseid, *key_values, needs_recheck, note, whseid, *key_values, whseid, *key_values, adddate, needs_recheck, note])
        else:
            cursor.execute(f'DELETE FROM {TARGET_SCHEMA}.{PENDING_TABLE} WHERE whseid = %s AND {match_clause}', [whseid, *key_values])

def _get_pending_windows(target_conn: Any, month_start_date: str, before_date: str) -> list[tuple[str, str]]:
    cursor = target_conn.cursor()
    cursor.execute(f'SELECT DISTINCT whseid, adddate FROM {TARGET_SCHEMA}.{PENDING_TABLE} WHERE adddate >= %s AND adddate < %s AND ReCheck = 1 ORDER BY whseid, adddate DESC', (month_start_date, before_date))
    result = []
    for whseid, adddate in cursor.fetchall():
        d = adddate.isoformat() if hasattr(adddate, 'isoformat') else str(adddate)[:10]
        result.append((whseid, d))
    return result

def _log_run(target_conn: Any, whseid: str, start_at: str, end_at: str, row_count: int, status: str) -> None:
    cursor = target_conn.cursor()
    cursor.execute(f'\n        INSERT INTO {TARGET_SCHEMA}.{LOG_TABLE} (whseid, start_at, end_at, row_count, status, loaded_at)\n        VALUES (%s, %s, %s, %s, %s, SYSUTCDATETIME())\n        ', (whseid, start_at, end_at, row_count, status))

def _daterange_desc(start_at: str, end_at: str) -> list[tuple[str, str]]:
    start_date = dt.datetime.strptime(start_at, '%Y-%m-%d %H:%M:%S').date()
    end_date = dt.datetime.strptime(end_at, '%Y-%m-%d %H:%M:%S').date()
    windows = []
    d = end_date
    while d >= start_date:
        windows.append((f'{d} 00:00:00', f'{d} 23:59:59'))
        d -= dt.timedelta(days=1)
    return windows

def _delete_window(target_conn: Any, whseid: str, from_date: str, to_date: str) -> None:
    cursor = target_conn.cursor()
    cursor.execute(f'DELETE FROM {TARGET_SCHEMA}.{TARGET_TABLE} WHERE _whseid = %s AND adddate >= %s AND adddate < DATEADD(day, 1, %s)', (whseid, from_date[:10], to_date[:10]))

def _sync_one_window(target_conn: Any, token: str, whseid: str, from_date: str, to_date: str) -> int:
    try:
        rows = _fetch_inbound(token, whseid, from_date, to_date)
        if rows:
            _delete_window(target_conn, whseid, from_date, to_date)
        _merge_rows(target_conn, whseid, rows)
        target_conn.commit()
        _log_run(target_conn, whseid, from_date, to_date, len(rows), 'SUCCESS')
        target_conn.commit()
        _sync_pending_table(target_conn, whseid, rows)
        target_conn.commit()
        return len(rows)
    except Exception:
        target_conn.rollback()
        _log_run(target_conn, whseid, from_date, to_date, 0, 'FAILED')
        target_conn.commit()
        raise

def sync_wms_inbound(target_conn: Any, *, start_at: str, end_at: str, warehouse_codes: list[str] | None=None, **_ignored: Any) -> int:
    _assert_table_exists(target_conn)
    token = _login()
    codes = warehouse_codes or PGI_WAREHOUSE_CODES
    _REQUEST_DELAY_SEC = 1.0
    total = 0
    for day_start, day_end in _daterange_desc(start_at, end_at):
        for whseid in codes:
            row_count = _sync_one_window(target_conn, token, whseid, day_start, day_end)
            total += row_count
            time.sleep(_REQUEST_DELAY_SEC)
        logger.info('WMS inbound ngay %s: xong %d kho', day_start[:10], len(codes))
    window_start_date = start_at[:10]
    month_start_date = f'{start_at[:7]}-01'
    pending_windows = _get_pending_windows(target_conn, month_start_date, window_start_date)
    for whseid, day in pending_windows:
        day_start, day_end = (f'{day} 00:00:00', f'{day} 23:59:59')
        row_count = _sync_one_window(target_conn, token, whseid, day_start, day_end)
        total += row_count
        time.sleep(_REQUEST_DELAY_SEC)
        logger.info('WMS inbound re-pull Pending kho %s ngay %s: %d dong', whseid, day, row_count)
    logger.info('Da dong bo tong %d dong vao %s.%s cho %d kho (+ %d cua so Pending), cua so chinh %s -> %s', total, TARGET_SCHEMA, TARGET_TABLE, len(codes), len(pending_windows), start_at, end_at)
    return total
