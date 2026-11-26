from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from services.pipeline.common.constants import TARGET_SCHEMA
from services.pipeline.common.db import assert_tables_exist, enable_fast_executemany

logger = logging.getLogger(__name__)

SOURCE_QUERY = """
    SELECT *
    FROM public.pgi_oms_synced_documents(%s::timestamp, %s::timestamp, %s::integer[], %s::boolean)
"""
TARGET_TABLE = 'DMS_SO_ALL'
LOG_TABLE = 'DMS_SO_ALL_Load_Log'
COMPANY_IDS = [1]
INCLUDE_CANCELLED = True
COLUMNS = (
    'model',
    'document_id',
    'document_type',
    'document_code',
    'order_type',
    'document_date',
    'created_at',
    'state_code',
    'state',
    'partner_code',
    'partner_name',
    'source_warehouse_code',
    'source_warehouse',
    'destination_warehouse_code',
    'destination_warehouse',
    'salesperson',
    'amount_total',
    'currency',
    'oms_count',
    'oms_codes',
    'oms_states',
    'company',
)


def _window_bounds(start_at: str, end_at: str) -> tuple[dt.datetime, dt.datetime]:
    try:
        start = dt.datetime.fromisoformat(start_at)
        end = dt.datetime.fromisoformat(end_at)
    except ValueError as exc:
        raise ValueError('start_at and end_at must be ISO date or datetime values.') from exc
    if start.tzinfo or end.tzinfo:
        raise ValueError('start_at and end_at must use local time without a timezone.')
    if start >= end:
        raise ValueError('start_at must be earlier than end_at.')
    return start, end


def _fetch_source_rows(source_conn: Any, start_at: dt.datetime, end_at: dt.datetime) -> tuple[list[str], list[tuple[Any, ...]]]:
    with source_conn.cursor() as cursor:
        cursor.execute(
            SOURCE_QUERY,
            (start_at, end_at - dt.timedelta(microseconds=1), COMPANY_IDS, INCLUDE_CANCELLED),
        )
        columns = [desc[0] for desc in cursor.description]
        if tuple(columns) != COLUMNS:
            raise RuntimeError(f'{TARGET_TABLE} source columns changed; received: {columns}')
        rows = [tuple(row) for row in cursor.fetchall()]
    product_metrics = _fetch_product_metrics(source_conn, rows)
    column_indexes = {name: index for index, name in enumerate(columns)}
    enriched_rows = []
    for row in rows:
        model = row[column_indexes['model']]
        document_id = row[column_indexes['document_id']]
        order_type = row[column_indexes['order_type']]
        state_code = row[column_indexes['state_code']]
        key = (model, document_id)
        if model in ('sale.order', 'pos.order') and state_code != 'cancel' and order_type not in ('L10', 'L14'):
            sku_count, quantity_total = product_metrics.get(key, (0, 0))
        else:
            sku_count, quantity_total = None, None
        enriched_rows.append((*row, sku_count, quantity_total))
    return [*columns, 'sku_count', 'quantity_total'], enriched_rows


def _fetch_product_metrics(source_conn: Any, rows: list[tuple[Any, ...]]) -> dict[tuple[str, int], tuple[int, Any]]:
    order_ids = {
        model: sorted(
            {
                row[1]
                for row in rows
                if row[0] == model and row[7] != 'cancel' and row[4] not in ('L10', 'L14')
            }
        )
        for model in ('sale.order', 'pos.order')
    }
    metrics: dict[tuple[str, int], tuple[int, Any]] = {}
    with source_conn.cursor() as cursor:
        if order_ids['sale.order']:
            cursor.execute(
                """
                SELECT line.order_id, COUNT(DISTINCT product.default_code), COALESCE(SUM(line.product_uom_qty), 0)
                FROM public.sale_order_line line
                JOIN public.product_product product ON product.id = line.product_id
                WHERE line.order_id = ANY(%s) AND line.display_type IS NULL
                GROUP BY line.order_id
                """,
                (order_ids['sale.order'],),
            )
            metrics.update({('sale.order', row[0]): (int(row[1] or 0), row[2] or 0) for row in cursor.fetchall()})
        if order_ids['pos.order']:
            cursor.execute(
                """
                SELECT line.order_id, COUNT(DISTINCT product.default_code), COALESCE(SUM(line.qty), 0)
                FROM public.pos_order_line line
                JOIN public.product_product product ON product.id = line.product_id
                WHERE line.order_id = ANY(%s)
                GROUP BY line.order_id
                """,
                (order_ids['pos.order'],),
            )
            metrics.update({('pos.order', row[0]): (int(row[1] or 0), row[2] or 0) for row in cursor.fetchall()})
    return metrics


def _sync_window(source_conn: Any, target_conn: Any, start_at: dt.datetime, end_at: dt.datetime) -> int:
    start_text, end_text = start_at.isoformat(sep=' '), end_at.isoformat(sep=' ')
    try:
        columns, rows = _fetch_source_rows(source_conn, start_at, end_at)
        cursor = target_conn.cursor()
        cursor.execute(
            f"""
            DELETE FROM {TARGET_SCHEMA}.{TARGET_TABLE}
            WHERE report_date >= %s AND report_date < %s
            """,
            (start_text, end_text),
        )
        if rows:
            quoted_cols = ', '.join(f'[{column}]' for column in columns)
            placeholders = ', '.join('%s' for _ in columns)
            cursor = target_conn.cursor()
            enable_fast_executemany(cursor)
            cursor.executemany(
                f'INSERT INTO {TARGET_SCHEMA}.{TARGET_TABLE} ({quoted_cols}) VALUES ({placeholders})',
                rows,
            )
        cursor = target_conn.cursor()
        cursor.execute(
            f"""
            INSERT INTO {TARGET_SCHEMA}.{LOG_TABLE} (start_at, end_at, row_count, status, loaded_at)
            VALUES (%s, %s, %s, %s, SYSUTCDATETIME())
            """,
            (start_text, end_text, len(rows), 'SUCCESS'),
        )
        target_conn.commit()
    except Exception:
        target_conn.rollback()
        cursor = target_conn.cursor()
        cursor.execute(
            f"""
            INSERT INTO {TARGET_SCHEMA}.{LOG_TABLE} (start_at, end_at, row_count, status, loaded_at)
            VALUES (%s, %s, %s, %s, SYSUTCDATETIME())
            """,
            (start_text, end_text, 0, 'FAILED'),
        )
        target_conn.commit()
        raise
    return len(rows)


def sync_dms_synced_documents(
    source_conn: Any,
    target_conn: Any,
    *,
    start_at: str,
    end_at: str,
    **_ignored: Any,
) -> int:
    start, end = _window_bounds(start_at, end_at)
    assert_tables_exist(target_conn, (TARGET_TABLE, LOG_TABLE), hint='chay db_migrations truoc.')
    cursor = target_conn.cursor()
    cursor.execute(
        "SELECT COL_LENGTH(%s, %s), COL_LENGTH(%s, %s)",
        (f'{TARGET_SCHEMA}.{TARGET_TABLE}', 'sku_count', f'{TARGET_SCHEMA}.{TARGET_TABLE}', 'quantity_total'),
    )
    if any(column_length is None for column_length in cursor.fetchone()):
        raise RuntimeError('DMS product metric columns are missing - chay db_migrations truoc.')
    row_count = _sync_window(source_conn, target_conn, start, end)
    logger.info(
        'Da nap %d dong vao %s.%s cho window %s -> %s',
        row_count,
        TARGET_SCHEMA,
        TARGET_TABLE,
        start,
        end,
    )
    return row_count
