from __future__ import annotations
import datetime as dt
import logging
import os
import time
from decimal import Decimal, InvalidOperation
from typing import Any
import requests
from services.pipeline.wms_inbound import PGI_WAREHOUSE_CODES, _login
logger = logging.getLogger(__name__)
WMS_TRANSACTION_URL = os.environ.get('WMS_TRANSACTION_URL', 'https://prod-swa-app-be-report.smartlogvn.com/api/transaction/itrns/list')
WMS_STORERKEY = os.environ.get('WMS_STORERKEY', 'PGI')
TARGET_SCHEMA = 'dbo'
TARGET_TABLE = 'WMS_TRANSACTION'
LOG_TABLE = 'WMS_TRANSACTION_Load_Log'
PAGE_SIZE = 5000
MAX_SQL_PARAMS = 2090
LOCAL_UTC_OFFSET = dt.timedelta(hours=7)
DATETIME_COLUMNS = ('adddate', 'editdate', 'lottable04', 'lottable05', 'lottable11', 'lottable12', 'tolottable04', 'tolottable05', 'tolottable11', 'tolottable12')
DECIMAL_COLUMNS = ('qty', 'toqty', 'uomqty', 'touomqty')
COLUMNS = ('id', 'itrnkey', 'trantype', 'sourcetype', 'sourcekey', 'whseid', 'fromwhseid', 'towhseid', 'storerkey', 'tostorerkey', 'sku', 'tosku', 'status', 'tostatus', 'qty', 'toqty', 'uom', 'uomqty', 'touom', 'touomqty', 'fromloc', 'toloc', 'fromlpnid', 'tolpnid', 'lot', 'tolot', 'palletid', 'topalletid', 'cartonid', 'tocartonid', 'unitid', 'tounitid', 'intransit', 'loadid', 'mastercode', 'remark', 'lottable01', 'lottable02', 'lottable03', 'lottable04', 'lottable05', 'lottable06', 'lottable07', 'lottable08', 'lottable09', 'lottable10', 'lottable11', 'lottable12', 'tolottable01', 'tolottable02', 'tolottable03', 'tolottable04', 'tolottable05', 'tolottable06', 'tolottable07', 'tolottable08', 'tolottable09', 'tolottable10', 'tolottable11', 'tolottable12', 'adddate', 'addwho', 'editdate', 'editwho')
_MAX_FETCH_RETRIES = 3
_FETCH_RETRY_DELAY_SEC = 3
_BUSY_MAX_RETRIES = 5
_BUSY_RETRY_DELAY_SEC = 20
_MAX_RELOGINS = 3
_RELOGIN_DELAY_SEC = 5
_REQUEST_DELAY_SEC = 1.0
_MAX_CONSISTENCY_CALLS = 6
_CONSISTENT_REPEATS = 3
_CONSISTENCY_DELAY_SEC = 0.3
_TOKEN_CACHE: dict[str, str] = {}

def _fetch_page_once(token: str, whseid: str, day: dt.date, page_index: int) -> list[dict]:
    body = {'orders': {}, 'filters': {}, 'pageIndex': page_index, 'pageSize': PAGE_SIZE, 'customFilter': {'whseid': whseid, 'storerkey': f"'{WMS_STORERKEY}'", 'beginDate': f'{day:%Y/%m/%d} 00:00:00', 'endDate': f'{day + dt.timedelta(days=1):%Y/%m/%d} 00:00:00'}}
    response = requests.post(WMS_TRANSACTION_URL, json=body, headers={'token': token, 'whseid': whseid}, timeout=120)
    response.raise_for_status()
    payload = response.json()
    rows = payload.get('data')
    if not isinstance(rows, list):
        raise RuntimeError(f"WMS transaction response khong co mang 'data': {str(payload)[:500]}")
    return rows

def _fetch_page(token: str, whseid: str, day: dt.date, page_index: int) -> list[dict]:
    busy_retries = 0
    other_retries = 0
    relogins = 0
    while True:
        try:
            return _fetch_page_once(_TOKEN_CACHE.get('token') or token, whseid, day, page_index)
        except requests.exceptions.RequestException as exc:
            response = getattr(exc, 'response', None)
            status = response.status_code if response is not None else None
            if status == 401 and relogins < _MAX_RELOGINS:
                relogins += 1
                logger.warning('WMS transaction kho %s ngay %s: token bi tu choi (401) - dang nhap lai (lan %d/%d).', whseid, day, relogins, _MAX_RELOGINS)
                time.sleep(_RELOGIN_DELAY_SEC * relogins)
                _TOKEN_CACHE['token'] = _login()
                continue
            if response is not None and 'server is busy' in response.text.lower():
                busy_retries += 1
                if busy_retries > _BUSY_MAX_RETRIES:
                    raise
                logger.warning('WMS transaction kho %s ngay %s: server bao busy (lan %d/%d), cho %ds.', whseid, day, busy_retries, _BUSY_MAX_RETRIES, _BUSY_RETRY_DELAY_SEC)
                time.sleep(_BUSY_RETRY_DELAY_SEC)
                continue
            other_retries += 1
            if other_retries > _MAX_FETCH_RETRIES:
                raise
            logger.warning('WMS transaction kho %s ngay %s: %s (lan %d/%d), thu lai sau %ds.', whseid, day, status or type(exc).__name__, other_retries, _MAX_FETCH_RETRIES, _FETCH_RETRY_DELAY_SEC)
            time.sleep(_FETCH_RETRY_DELAY_SEC)

def _fetch_day_raw(token: str, whseid: str, day: dt.date) -> list[dict]:
    rows: list[dict] = []
    page_index = 1
    while True:
        page = _fetch_page(token, whseid, day, page_index)
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        page_index += 1
        time.sleep(_REQUEST_DELAY_SEC)
    return rows

def _row_id(row: dict) -> str | None:
    return row.get('id') or row.get('ID')

def _row_adddate(row: dict) -> dt.datetime | None:
    return _to_datetime(row.get('adddate') or row.get('ADDDATE'))

def _signature(rows: list[dict]) -> frozenset:
    return frozenset(((_row_id(r), str(r.get('adddate') or r.get('ADDDATE'))) for r in rows))

def _ids_stored_on_other_day(target_conn: Any, whseid: str, day: dt.date, rows: list[dict]) -> int:
    ids = [i for i in {_row_id(r) for r in rows} if i]
    if not ids:
        return 0
    cursor = target_conn.cursor()
    found = 0
    for i in range(0, len(ids), 1000):
        chunk = ids[i:i + 1000]
        cursor.execute(f"SELECT COUNT(*) FROM {TARGET_SCHEMA}.{TARGET_TABLE} WHERE id IN ({', '.join(['%s'] * len(chunk))}) AND NOT (_whseid = %s AND _txn_date = %s)", (*chunk, whseid, day))
        found += cursor.fetchone()[0]
    return found

def _pick_variant(target_conn: Any, whseid: str, day: dt.date, variants: list[list[dict]]) -> list[dict]:
    clean = [v for v in variants if _ids_stored_on_other_day(target_conn, whseid, day, v) == 0]
    candidates = clean or variants
    if len(candidates) == 1:
        return candidates[0]
    def earlier_score(v: list[dict]) -> int:
        mine = {_row_id(r): _row_adddate(r) for r in v}
        score = 0
        for other in candidates:
            if other is v:
                continue
            for r in other:
                a, b = mine.get(_row_id(r)), _row_adddate(r)
                if a is not None and b is not None and a < b:
                    score += 1
        return score
    return max(candidates, key=earlier_score)

def _fetch_day(target_conn: Any, token: str, whseid: str, day: dt.date) -> list[dict]:
    variants: dict[frozenset, list[dict]] = {}
    counts: dict[frozenset, int] = {}
    for attempt in range(_MAX_CONSISTENCY_CALLS):
        rows = _fetch_day_raw(token, whseid, day)
        sig = _signature(rows)
        variants.setdefault(sig, rows)
        counts[sig] = counts.get(sig, 0) + 1
        if counts[sig] >= _CONSISTENT_REPEATS and _ids_stored_on_other_day(target_conn, whseid, day, rows) == 0:
            break
        if len(variants) >= 2 and attempt + 1 >= _CONSISTENT_REPEATS:
            break
        time.sleep(_CONSISTENCY_DELAY_SEC)
    if len(variants) > 1:
        logger.warning('WMS transaction kho %s ngay %s: API tra %d ket qua khac nhau qua %d lan goi - chon ban dung.', whseid, day, len(variants), sum(counts.values()))
    rows = _pick_variant(target_conn, whseid, day, list(variants.values()))
    unique = {}
    dropped = 0
    for row in rows:
        key = _row_id(row)
        adddate = _row_adddate(row)
        row_whse = row.get('whseid') or row.get('WHSEID') or whseid
        if not key or adddate is None or (adddate + LOCAL_UTC_OFFSET).date() != day or row_whse != whseid:
            dropped += 1
            continue
        unique[key] = row
    if dropped:
        logger.warning('WMS transaction kho %s ngay %s: bo %d dong API tra ve nam ngoai ngay/kho dang keo.', whseid, day, dropped)
    return list(unique.values())

def _to_datetime(value: Any) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).replace('Z', '+00:00')
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return parsed

def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None

def _to_db_row(whseid: str, day: dt.date, row: dict) -> tuple:
    row_ci = {}
    for key, value in row.items():
        if key == key.lower() or key.lower() not in row_ci:
            row_ci[key.lower()] = value
    values = []
    for col in COLUMNS:
        value = row_ci.get(col)
        if col in DATETIME_COLUMNS:
            value = _to_datetime(value)
        elif col in DECIMAL_COLUMNS:
            value = _to_decimal(value)
        values.append(value)
    return (whseid, day, *values)

def _assert_table_exists(target_conn: Any) -> None:
    cursor = target_conn.cursor()
    for table in (TARGET_TABLE, LOG_TABLE):
        cursor.execute("SELECT OBJECT_ID(%s, 'U')", (f'{TARGET_SCHEMA}.{table}',))
        if cursor.fetchone()[0] is None:
            raise RuntimeError(f'Bang {TARGET_SCHEMA}.{table} chua ton tai - chay db_migrations truoc.')

def _replace_day(target_conn: Any, whseid: str, day: dt.date, rows: list[dict]) -> None:
    cursor = target_conn.cursor()
    cursor.execute(f'DELETE FROM {TARGET_SCHEMA}.{TARGET_TABLE} WHERE _whseid = %s AND _txn_date = %s', (whseid, day))
    if not rows:
        return
    insert_cols = ', '.join(('_whseid', '_txn_date', *(f'[{c}]' for c in COLUMNS)))
    per_row = len(COLUMNS) + 2
    batch_size = max(1, MAX_SQL_PARAMS // per_row)
    placeholder = '(' + ', '.join(['%s'] * per_row) + ')'
    db_rows = [_to_db_row(whseid, day, row) for row in rows]
    replaced = 0
    for i in range(0, len(db_rows), batch_size):
        batch = db_rows[i:i + batch_size]
        ids = [r[2] for r in batch]
        cursor.execute(f"DELETE FROM {TARGET_SCHEMA}.{TARGET_TABLE} WHERE id IN ({', '.join(['%s'] * len(ids))})", tuple(ids))
        replaced += cursor.rowcount or 0
        cursor.execute(f'INSERT INTO {TARGET_SCHEMA}.{TARGET_TABLE} ({insert_cols}) VALUES ' + ', '.join([placeholder] * len(batch)), tuple((v for r in batch for v in r)))
    if replaced:
        logger.warning('WMS transaction kho %s ngay %s: %d id da co o ngay/kho khac, ghi de bang ban moi.', whseid, day, replaced)

def _log_run(target_conn: Any, whseid: str, day: dt.date, row_count: int, status: str) -> None:
    cursor = target_conn.cursor()
    cursor.execute(f'INSERT INTO {TARGET_SCHEMA}.{LOG_TABLE} (whseid, txn_date, row_count, status, loaded_at) VALUES (%s, %s, %s, %s, SYSUTCDATETIME())', (whseid, day, row_count, status))

def _days(start_date: str, end_date: str) -> list[dt.date]:
    start = dt.date.fromisoformat(start_date[:10])
    end = dt.date.fromisoformat(end_date[:10])
    if start > end:
        raise ValueError(f'start_date {start} > end_date {end}')
    return [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]

def sync_wms_transaction(target_conn: Any, *, start_date: str, end_date: str, warehouse_codes: list[str] | None=None, **_ignored: Any) -> int:
    _assert_table_exists(target_conn)
    token = _login()
    _TOKEN_CACHE['token'] = token
    codes = warehouse_codes or PGI_WAREHOUSE_CODES
    total = 0
    for day in _days(start_date, end_date):
        day_total = 0
        for whseid in codes:
            try:
                rows = _fetch_day(target_conn, token, whseid, day)
                _replace_day(target_conn, whseid, day, rows)
                target_conn.commit()
                _log_run(target_conn, whseid, day, len(rows), 'SUCCESS')
                target_conn.commit()
            except Exception:
                target_conn.rollback()
                _log_run(target_conn, whseid, day, 0, 'FAILED')
                target_conn.commit()
                raise
            day_total += len(rows)
            time.sleep(_REQUEST_DELAY_SEC)
        total += day_total
        logger.info('WMS transaction ngay %s: %d dong (%d kho)', day, day_total, len(codes))
    logger.info('Da dong bo %d dong vao %s.%s, %s -> %s', total, TARGET_SCHEMA, TARGET_TABLE, start_date, end_date)
    return total
