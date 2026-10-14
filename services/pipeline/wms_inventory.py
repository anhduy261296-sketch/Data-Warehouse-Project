from __future__ import annotations
import logging
import os
import time
from typing import Any
import requests
from services.pipeline.common.constants import PGI_WAREHOUSE_CODES, TARGET_SCHEMA
from services.pipeline.common.db import assert_tables_exist, enable_fast_executemany
from services.pipeline.common.wms_client import REQUEST_DELAY_SEC, WMS_STORERKEY, call_with_retry, start_session

logger = logging.getLogger(__name__)
WMS_INVENTORY_URL = os.environ.get('WMS_INVENTORY_URL', 'https://poms-be.smartlogix.biz/api/standardized/v1/reports/inventories')
WMS_INVENTORY_FIELD_NAMES = [
    'whseid',
    'storerkey',
    'receiptdate',
    'externreceiptkey',
    'rc_type',
    'sku',
    'description',
    'status',
    'lot',
    'loc',
    'palletid',
    'cartonid',
    'unitid',
    'uomqty',
    'uom',
    'qty',
    'lottable01',
    'lottable02',
    'lottable03',
    'lottable04',
    'lottable05',
    'lottable06',
    'lottable07',
    'lottable08',
    'lottable09',
    'lottable10',
    'lottable11',
    'lottable12',
    'skuprice',
    'price',
    'qtyallocated',
    'qtypicked',
    'qtyavailable',
    'billoflading',
    'bookingno',
    'category',
    'upccode',
    'manufacturersku',
    'altsku',
    'stdcube',
    'cube',
    'packkey',
    'innerpack',
    'pallet',
    'shelflife',
    'manageimei',
    'manageimeiout',
]
_IGNORED_RESPONSE_FIELDS = {'whseid'}
_BUSINESS_KEY = ('storerkey', 'sku', 'lot', 'loc', 'palletid', 'cartonid', 'unitid', 'lpnid')
_TRACKED_FIELDS = ('qty', 'status')
WMS_INVENTORY_PAGE_SIZE = 5000
TARGET_TABLE = 'WMS_INVENTORY'
LOG_TABLE = 'WMS_INVENTORY_Load_Log'
CHANGELOG_TABLE = 'WMS_INVENTORY_ChangeLog'


def _fetch_inventory_once(token: str, whseid: str) -> tuple[list[dict], int | None]:
    response = requests.post(
        WMS_INVENTORY_URL,
        json={
            'whseid': whseid,
            'storerkey': [WMS_STORERKEY],
            'page': 1,
            'pageSize': WMS_INVENTORY_PAGE_SIZE,
            'fieldNames': WMS_INVENTORY_FIELD_NAMES,
        },
        headers={'token': token, 'whseid': whseid},
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get('data')
    if not isinstance(rows, list):
        raise RuntimeError(f"WMS inventory response khong co mang 'data': {str(payload)[:500]}")
    return (rows, payload.get('total'))


def _fetch_inventory(token: str, whseid: str) -> list[dict]:
    rows, total = call_with_retry(lambda t: _fetch_inventory_once(t, whseid), token, label=f'WMS inventory kho {whseid}')
    if total is not None and total != len(rows):
        logger.warning(
            'WMS inventory kho %s: total=%s nhung chi nhan %d dong - API khong ho tro chia cua so cho Inventory, du lieu co the thieu.',
            whseid,
            total,
            len(rows),
        )
    return rows


def _assert_table_exists(target_conn: Any) -> None:
    assert_tables_exist(target_conn, (TARGET_TABLE, CHANGELOG_TABLE, LOG_TABLE), hint='chay DDL truoc.')


def _diff_and_log_changes(target_conn: Any, whseid: str, new_rows: list[dict]) -> int:
    cursor = target_conn.cursor()
    old_cols = ', '.join((f'[{c}]' for c in (*_BUSINESS_KEY, *_TRACKED_FIELDS)))
    cursor.execute(f'SELECT {old_cols} FROM {TARGET_SCHEMA}.{TARGET_TABLE} WHERE _whseid = %s', (whseid,))
    old_columns = [d[0] for d in cursor.description]
    old_by_key: dict[tuple, dict] = {}
    for row in cursor.fetchall():
        values = dict(zip(old_columns, row))
        old_by_key[tuple((values.get(k) for k in _BUSINESS_KEY))] = values
    new_by_key: dict[tuple, dict] = {tuple((row.get(k) for k in _BUSINESS_KEY)): row for row in new_rows}
    old_keys = set(old_by_key)
    new_keys = set(new_by_key)
    changes: list[tuple] = []
    for key in old_keys - new_keys:
        old = old_by_key[key]
        changes.append((*key, 'REMOVED', *(old.get(f) for f in _TRACKED_FIELDS), *(None for _ in _TRACKED_FIELDS)))
    for key in new_keys - old_keys:
        new = new_by_key[key]
        changes.append((*key, 'ADDED', *(None for _ in _TRACKED_FIELDS), *(new.get(f) for f in _TRACKED_FIELDS)))
    for key in old_keys & new_keys:
        old, new = (old_by_key[key], new_by_key[key])
        if any((old.get(f) != new.get(f) for f in _TRACKED_FIELDS)):
            changes.append((*key, 'CHANGED', *(old.get(f) for f in _TRACKED_FIELDS), *(new.get(f) for f in _TRACKED_FIELDS)))
    if not changes:
        return 0
    key_cols = ', '.join((f'[{c}]' for c in _BUSINESS_KEY))
    old_val_cols = ', '.join((f'[old_{f}]' for f in _TRACKED_FIELDS))
    new_val_cols = ', '.join((f'[new_{f}]' for f in _TRACKED_FIELDS))
    sql = f"INSERT INTO {TARGET_SCHEMA}.{CHANGELOG_TABLE} (_whseid, {key_cols}, change_type, {old_val_cols}, {new_val_cols}, _change_date, detected_at) VALUES (%s, {', '.join(('%s' for _ in _BUSINESS_KEY))}, %s, {', '.join(('%s' for _ in _TRACKED_FIELDS))}, {', '.join(('%s' for _ in _TRACKED_FIELDS))}, CAST(SYSUTCDATETIME() AS DATE), SYSUTCDATETIME())"
    params = [(whseid, *change) for change in changes]
    cursor.executemany(sql, params)
    return len(changes)


def _replace_warehouse(target_conn: Any, whseid: str, rows: list[dict]) -> int:
    changed_count = _diff_and_log_changes(target_conn, whseid, rows)
    cursor = target_conn.cursor()
    cursor.execute(f'DELETE FROM {TARGET_SCHEMA}.{TARGET_TABLE} WHERE _whseid = %s', (whseid,))
    if not rows:
        return changed_count
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key in _IGNORED_RESPONSE_FIELDS:
                continue
            if key not in seen:
                seen.add(key)
                columns.append(key)
    insert_cols = ', '.join((f'[{c}]' for c in columns))
    placeholders = ', '.join(('%s' for _ in columns))
    sql = f'INSERT INTO {TARGET_SCHEMA}.{TARGET_TABLE} (_whseid, _storerkey, {insert_cols}, _scraped_at) VALUES (%s, %s, {placeholders}, SYSUTCDATETIME())'
    params = [(whseid, WMS_STORERKEY, *(row.get(c) for c in columns)) for row in rows]
    enable_fast_executemany(cursor)
    cursor.executemany(sql, params)
    return changed_count


def _log_run(target_conn: Any, whseid: str, row_count: int, status: str) -> None:
    cursor = target_conn.cursor()
    cursor.execute(
        f'\n        INSERT INTO {TARGET_SCHEMA}.{LOG_TABLE} (whseid, row_count, status, loaded_at)\n        VALUES (%s, %s, %s, SYSUTCDATETIME())\n        ',
        (whseid, row_count, status),
    )


def sync_wms_inventory(target_conn: Any, *, warehouse_codes: list[str] | None = None, **_ignored: Any) -> int:
    _assert_table_exists(target_conn)
    token = start_session()
    codes = warehouse_codes or PGI_WAREHOUSE_CODES
    total = 0
    for whseid in codes:
        try:
            rows = _fetch_inventory(token, whseid)
            changed_count = _replace_warehouse(target_conn, whseid, rows)
            target_conn.commit()
            _log_run(target_conn, whseid, len(rows), 'SUCCESS')
            target_conn.commit()
            total += len(rows)
            logger.info('WMS inventory kho %s: %d dong (%d thay doi so voi lan truoc)', whseid, len(rows), changed_count)
        except Exception:
            target_conn.rollback()
            _log_run(target_conn, whseid, 0, 'FAILED')
            target_conn.commit()
            raise
        time.sleep(REQUEST_DELAY_SEC)
    logger.info('Da dong bo tong %d dong vao %s.%s cho %d kho (full-refresh).', total, TARGET_SCHEMA, TARGET_TABLE, len(codes))
    return total
