from __future__ import annotations
import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable
from django.db import connection
from ..constants import EXPORT_MAX_ROWS, MAX_DATE_RANGE_DAYS, MAX_PAGE_LENGTH


@dataclass(frozen=True)
class DetailColumn:
    sql_expr: str
    data_key: str
    searchable: bool = False
    orderable: bool = True
    title: str = ''


@dataclass(frozen=True)
class DetailReportConfig:
    table: str
    where: str
    columns: list[DetailColumn] = field(default_factory=list)
    join_sql: str = ''
    status_sync_expr: str = 't.StatusSync'
    so_status_expr: str = 't.SoStatus'
    date_expr: str = ''
    status_values: tuple[str, ...] = ('Sync', 'Not Sync')
    default_hidden_status: str = ''
    default_order_sql: str = ''
    filter_params: tuple[tuple[str, str], ...] = ()
    cache_sources: tuple[str, ...] = ()
    row_key: str = ''


def get_distinct_so_status(config: DetailReportConfig) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            f'\n            SELECT DISTINCT {config.so_status_expr}\n            FROM {config.table} t\n            {config.join_sql}\n            WHERE {config.where} AND {config.so_status_expr} IS NOT NULL\n            ORDER BY {config.so_status_expr}\n            '
        )
        return [row[0] for row in cursor.fetchall()]


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    return value


def _build_where_extra(config: DetailReportConfig, params: dict[str, Any]) -> tuple[str, list[Any]]:
    search_value = (params.get('search[value]') or '').strip()
    status_sync_filter = (params.get('status_sync') or '').strip()
    so_status_filter = (params.get('so_status') or '').strip()
    date_from = (params.get('date_from') or '').strip()
    date_to = (params.get('date_to') or '').strip()
    if config.date_expr and date_from and date_to:
        try:
            d_from = datetime.date.fromisoformat(date_from)
            d_to = datetime.date.fromisoformat(date_to)
            if (d_to - d_from).days > MAX_DATE_RANGE_DAYS:
                date_from = (d_to - datetime.timedelta(days=MAX_DATE_RANGE_DAYS)).isoformat()
        except ValueError:
            pass
    where_extra = ''
    query_params: list[Any] = []
    if status_sync_filter in config.status_values:
        where_extra += f" AND ISNULL({config.status_sync_expr}, 'Not Sync') = %s"
        query_params.append(status_sync_filter)
    elif config.default_hidden_status:
        where_extra += f' AND {config.status_sync_expr} <> %s'
        query_params.append(config.default_hidden_status)
    for param_name, sql_expr in config.filter_params:
        value = (params.get(param_name) or '').strip()
        if value:
            where_extra += f' AND {sql_expr} = %s'
            query_params.append(value)
    if so_status_filter:
        where_extra += f' AND {config.so_status_expr} = %s'
        query_params.append(so_status_filter)
    if config.date_expr and date_from:
        where_extra += f' AND {config.date_expr} >= %s'
        query_params.append(date_from)
    if config.date_expr and date_to:
        where_extra += f' AND {config.date_expr} < DATEADD(day, 1, %s)'
        query_params.append(date_to)
    searchable_cols = [c for c in config.columns if c.searchable]
    if search_value and searchable_cols:
        like_clauses = ' OR '.join((f'{c.sql_expr} LIKE %s' for c in searchable_cols))
        where_extra += f' AND ({like_clauses})'
        query_params.extend([f'%{search_value}%'] * len(searchable_cols))
    return (where_extra, query_params)


def run_detail_report(config: DetailReportConfig, params: dict[str, Any], counts: Callable | None = None) -> dict[str, Any]:
    draw = int(params.get('draw') or 1)
    start = max(int(params.get('start') or 0), 0)
    length = int(params.get('length') or 10)
    if length <= 0:
        length = MAX_PAGE_LENGTH
    length = min(length, MAX_PAGE_LENGTH)
    default_order_expr = (
        config.default_order_sql
        or f"CASE WHEN {config.status_sync_expr} = 'Not Sync' THEN 0 WHEN {config.status_sync_expr} IS NULL THEN 1 ELSE 2 END"
    )
    order_expr = default_order_expr
    order_dir = 'ASC'
    order_col_idx = params.get('order[0][column]')
    if order_col_idx is not None:
        try:
            col = config.columns[int(order_col_idx)]
        except (ValueError, IndexError):
            col = None
        if col is not None and col.orderable:
            order_expr = col.sql_expr
            order_dir = 'DESC' if (params.get('order[0][dir]') or '').lower() == 'desc' else 'ASC'
    select_list = ', '.join((f'{c.sql_expr} AS [{c.data_key}]' for c in config.columns))
    base_from = f'\n        FROM {config.table} t\n        {config.join_sql}\n        WHERE {config.where}\n    '
    where_extra, query_params = _build_where_extra(config, params)
    with connection.cursor() as cursor:

        def count_rows() -> tuple[int, int]:
            cursor.execute(f'SELECT COUNT(*) {base_from}')
            total = cursor.fetchone()[0]
            cursor.execute(f'SELECT COUNT(*) {base_from} {where_extra}', query_params)
            return total, cursor.fetchone()[0]

        records_total, records_filtered = counts(count_rows) if counts else count_rows()
        if config.row_key:
            cursor.execute(
                f"""
                ;WITH p AS (
                    SELECT t.{config.row_key} AS __k, ROW_NUMBER() OVER (ORDER BY {order_expr} {order_dir}, t.{config.row_key}) AS __rn
                    {base_from}
                    {where_extra}
                    ORDER BY __rn OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
                )
                SELECT {select_list}
                FROM p JOIN {config.table} t ON t.{config.row_key} = p.__k
                {config.join_sql}
                ORDER BY p.__rn
                """,
                [*query_params, start, length],
            )
        else:
            cursor.execute(
                f'\n            SELECT {select_list}\n            {base_from}\n            {where_extra}\n            ORDER BY {order_expr} {order_dir}\n            OFFSET %s ROWS FETCH NEXT %s ROWS ONLY\n            ',
                [*query_params, start, length],
            )
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    for row in rows:
        for key, value in row.items():
            row[key] = _json_safe(value)
    return {'draw': draw, 'recordsTotal': records_total, 'recordsFiltered': records_filtered, 'data': rows}


def export_detail_report_rows(config: DetailReportConfig, params: dict[str, Any], max_rows: int = EXPORT_MAX_ROWS) -> list[dict]:
    select_list = ', '.join((f'{c.sql_expr} AS [{c.data_key}]' for c in config.columns))
    base_from = f'\n        FROM {config.table} t\n        {config.join_sql}\n        WHERE {config.where}\n    '
    where_extra, query_params = _build_where_extra(config, params)
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT TOP {max_rows} {select_list} {base_from} {where_extra}', query_params)
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    for row in rows:
        for key, value in row.items():
            row[key] = _json_safe(value)
    return rows
