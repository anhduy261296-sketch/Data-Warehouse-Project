"""Danh muc kenh ban hang OMS (offline + online) -> dbo.OMS_SALES_CHANNELS. It thay doi nen KHONG co lich - chay tay khi can:

  - Web: Bao cao > E-commerce > nut "Cap nhat kenh ban" (quan tri vien) -> kich hoat DAG oms_sales_channels_manual
  - Airflow UI: Trigger DAG oms_sales_channels_manual
  - Lenh: docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -w /opt/airflow/project airflow-scheduler \
              python -m services.pipeline.oms_sales_channels

Chay trong Airflow vi dung chung refresh token OMS va connection sqlserver_tracking voi pipeline oms_orders.
"""

from __future__ import annotations
import logging
import os
from typing import Any
from services.pipeline.common.constants import TARGET_SCHEMA
from services.pipeline.common.db import assert_tables_exist
from services.pipeline.oms_orders import _login_oms, _oms_get

logger = logging.getLogger(__name__)
OMS_SALES_CHANNELS_URL = os.environ.get('OMS_SALES_CHANNELS_URL', 'https://som-api.smartlogvn.com/api/sales-channels')
OFFLINE_PAGE_SIZE = 100
TARGET_TABLE = 'OMS_SALES_CHANNELS'
# Kenh online OMS tra description la khoa dich (SETTING.SALE_CHANNEL.ONLINE.TIK_DES) -> dat ten hien thi (ngan) o day
DISPLAY_NAMES = {'TIK': 'Tiki', 'TTS': 'TikTok', 'LAZ': 'Lazada', 'SPE': 'Shopee', 'PANCAKE': 'Pancake'}
COLUMNS = ('code', 'display_name', 'description', 'operation', 'status', 'priority_order', 'oms_id', 'created_date', 'updated_date')


def _fetch_online(access_token: str) -> list[dict]:
    payload = _oms_get(access_token, OMS_SALES_CHANNELS_URL)
    return (payload.get('data') or []) if isinstance(payload, dict) else payload


def _fetch_offline(access_token: str) -> list[dict]:
    rows: list[dict] = []
    page_index = 1
    while True:
        payload = _oms_get(
            access_token,
            f'{OMS_SALES_CHANNELS_URL}/offline',
            {'page_index': page_index, 'page_size': OFFLINE_PAGE_SIZE, 'filter': '[]', 'sort': '[]', 'text_search': ''},
        )
        page = payload.get('data') or []
        rows.extend(page)
        if not page or len(rows) >= (payload.get('total_count') or 0):
            return rows
        page_index += 1


def _display_name(code: str, description: str | None) -> str:
    if code in DISPLAY_NAMES:
        return DISPLAY_NAMES[code]
    if description and not description.startswith('SETTING.'):
        return description.strip()
    return code


def _to_row(item: dict, default_operation: str) -> tuple:
    code = str(item.get('code') or '').strip()
    description = item.get('description')
    return (
        code,
        _display_name(code, description),
        description,
        item.get('operation') or default_operation,
        item.get('status'),
        item.get('priority_order'),
        str(item['id']) if item.get('id') is not None else None,
        item.get('created_date'),
        item.get('updated_date'),
    )


def build_rows(online: list[dict], offline: list[dict]) -> list[tuple]:
    rows = [_to_row(i, 'online') for i in online] + [_to_row(i, 'offline') for i in offline]
    rows = [r for r in rows if r[0]]
    codes = [r[0] for r in rows]
    duplicated = sorted({c for c in codes if codes.count(c) > 1})
    if duplicated:
        raise RuntimeError(f'Ma kenh ban trung giua online/offline: {duplicated} - khong ghi de {TARGET_TABLE}.')
    return rows


def sync_oms_sales_channels(target_conn: Any, **_ignored: Any) -> int:
    assert_tables_exist(target_conn, [TARGET_TABLE])
    access_token = _login_oms()
    rows = build_rows(_fetch_online(access_token), _fetch_offline(access_token))
    if not rows:
        raise RuntimeError(f'OMS khong tra ve kenh ban nao - khong ghi de {TARGET_TABLE}.')
    cursor = target_conn.cursor()
    try:
        cursor.execute(f'DELETE FROM {TARGET_SCHEMA}.{TARGET_TABLE}')
        cursor.executemany(
            f'INSERT INTO {TARGET_SCHEMA}.{TARGET_TABLE} ({", ".join(COLUMNS)}, loaded_at) '
            f'VALUES ({", ".join(["%s"] * len(COLUMNS))}, SYSUTCDATETIME())',
            rows,
        )
        target_conn.commit()
    except Exception:
        target_conn.rollback()
        raise
    logger.info('Da dong bo %d kenh ban OMS vao %s.%s', len(rows), TARGET_SCHEMA, TARGET_TABLE)
    return len(rows)


if __name__ == '__main__':
    from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

    logging.basicConfig(level=logging.INFO)
    connection = MsSqlHook(mssql_conn_id='sqlserver_tracking').get_conn()
    try:
        count = sync_oms_sales_channels(connection)
        cur = connection.cursor()
        cur.execute(
            f'SELECT code, display_name, operation, status FROM {TARGET_SCHEMA}.{TARGET_TABLE} ORDER BY operation, priority_order, code'
        )
        for row in cur.fetchall():
            print(*row, sep=' | ')
        print(f'OMS sales channels -> SQL Server: {count} kenh.')
    finally:
        connection.close()
