"""Bao cao > Ton kho: KPI, bang SKU x kho, top SKU, theo kho, theo nhom, chi tiet theo kho & trang thai (nguon WMS_INVENTORY)."""

from __future__ import annotations
from typing import Any
from django.db import connection

from ..core.cache import SOURCES, cache_key, cached, get_or_set
from ..core.sql import num as _num, rows as _rows
from ..constants import (
    EXPORT_MAX_ROWS,
    MAX_PAGE_LENGTH,
    STOCK_TOP_LIMIT,
    WMS_WAREHOUSE_RE,
)

_WHSE_RE = WMS_WAREHOUSE_RE
_QTY = 'TRY_CONVERT(DECIMAL(21,4), w.qty)'
_AVAILABLE = 'TRY_CONVERT(DECIMAL(21,4), w.qtyavailable)'
_HELD = '(ISNULL(TRY_CONVERT(DECIMAL(21,4), w.qtyallocated), 0) + ISNULL(TRY_CONVERT(DECIMAL(21,4), w.qtypicked), 0))'
_FROM = 'FROM dbo.WMS_INVENTORY w'

_UOM_JOIN = 'LEFT JOIN dbo.SAP_UOM u ON u.UomCode = ISNULL(i.Uom, a.wms_uom)'
_UOM = 'ISNULL(u.UomName, ISNULL(i.Uom, a.wms_uom))'
_SORTABLE = {'sku': 'sku', 'item_name': 'item_name', 'total_qty': 'total_qty', 'available_qty': 'available_qty', 'held_qty': 'held_qty'}
TOP_LIMIT = STOCK_TOP_LIMIT


def _filters(params: Any) -> tuple[str, list[Any]]:
    where, args = ([], [])
    q = (params.get('q') or '').strip()
    if q:
        like = f'%{q}%'

        where.append(
            '(w.sku LIKE %s OR w.description LIKE %s OR EXISTS (SELECT 1 FROM dbo.SAP_ITEMS si WHERE si.ItemCode = w.sku AND (si.ItemName LIKE %s OR si.Barcode LIKE %s OR si.PgiCode LIKE %s)))'
        )
        args += [like] * 5
    group = (params.get('group') or '').strip()
    if group:
        where.append('w.sku IN (SELECT ItemCode FROM dbo.SAP_ITEMS WHERE ItemGroup1 = %s)')
        args.append(group)
    whs = (params.get('whs') or '').strip().upper()
    if _WHSE_RE.match(whs):
        where.append('w._whseid = %s')
        args.append(whs)
    status = (params.get('status') or '').strip()
    if status:
        where.append('w.status = %s')
        args.append(status)
    return (' AND '.join(where) or '1=1', args)


# Bao cao doc WMS_INVENTORY + ten hang / nhom / DVT tu SAP -> cache tu het han khi 1 trong cac nguon nay nap lai
STOCK_SOURCES = ('wms_inventory', 'sap_items', 'sap_item_groups', 'sap_uom')


def _warehouses(cursor: Any) -> list[dict[str, str]]:
    return get_or_set(cache_key('stock.warehouses', STOCK_SOURCES), lambda: _load_warehouses(cursor))


def _load_warehouses(cursor: Any) -> list[dict[str, str]]:
    cursor.execute('SELECT DISTINCT _whseid FROM dbo.WMS_INVENTORY')
    codes = sorted((r[0] for r in cursor.fetchall() if _WHSE_RE.match(r[0] or '')))
    cursor.execute('SELECT WhsCode, MAX(WhsName) FROM dbo.SAP_INVENTORY GROUP BY WhsCode')
    names = {code: name for code, name in cursor.fetchall()}
    return [{'code': code, 'name': names.get('W' + code[2:]) or code} for code in codes]


@cached(*STOCK_SOURCES)
def get_meta(_params: Any = None) -> dict[str, Any]:
    with connection.cursor() as cursor:
        warehouses = _warehouses(cursor)
        cursor.execute("""
            SELECT g.ItmsGrpCod, g.ItmsGrpNam FROM dbo.SAP_ITEM_GROUPS g
            WHERE EXISTS (SELECT 1 FROM dbo.SAP_ITEMS i WHERE i.ItemGroup1 = g.ItmsGrpCod) ORDER BY g.ItmsGrpCod
            """)
        groups = [{'code': c, 'name': n} for c, n in cursor.fetchall()]
        cursor.execute("SELECT DISTINCT status FROM dbo.WMS_INVENTORY WHERE ISNULL(status, '') <> '' ORDER BY status")
        statuses = [r[0] for r in cursor.fetchall()]
        cursor.execute(SOURCES['wms_inventory'])  # thoi diem nap ton WMS gan nhat (cung SQL voi phien ban cache)
        snapshot_at = cursor.fetchone()[0]
    return {
        'warehouses': warehouses,
        'groups': groups,
        'statuses': statuses,
        'snapshot_at': snapshot_at.isoformat() if snapshot_at else None,
    }


@cached(*STOCK_SOURCES)
def get_kpi(params: Any) -> dict[str, Any]:
    where, args = _filters(params)
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(DISTINCT w.sku), COUNT(DISTINCT w._whseid), ISNULL(SUM({_QTY}), 0) {_FROM} WHERE {where}', args)
        sku_count, whs_count, total_qty = cursor.fetchone()
    return {'sku_count': sku_count, 'warehouse_count': whs_count, 'total_qty': _num(total_qty)}


def _sku_agg(warehouses: list[str], where: str) -> str:
    codes = [c for c in warehouses if _WHSE_RE.match(c)]
    pivot = ''.join((f", SUM(CASE WHEN w._whseid = '{code}' THEN {_QTY} ELSE 0 END) AS [{code}]" for code in codes))
    pivot_out = ''.join((f', a.[{code}]' for code in codes))
    return f"""
        ;WITH a AS (
            SELECT w.sku, MAX(w.description) AS wms_name, MAX(w.uom) AS wms_uom,
                   SUM({_QTY}) AS total_qty, SUM({_AVAILABLE}) AS available_qty, SUM({_HELD}) AS held_qty{pivot}
            {_FROM} WHERE {where} GROUP BY w.sku
        )
        SELECT a.sku AS sku, ISNULL(i.ItemName, a.wms_name) AS item_name, {_UOM} AS uom,
               a.total_qty, a.available_qty, a.held_qty{pivot_out}
        FROM a LEFT JOIN dbo.SAP_ITEMS i ON i.ItemCode = a.sku {_UOM_JOIN}
        """


@cached(*STOCK_SOURCES)
def get_by_sku(params: Any) -> dict[str, Any]:
    where, args = _filters(params)
    try:
        start = max(0, int(params.get('start') or 0))
        length = min(MAX_PAGE_LENGTH, max(1, int(params.get('length') or 10)))
        draw = int(params.get('draw') or 0)
    except ValueError:
        start, length, draw = (0, 10, 0)
    sort_key = params.get(f"columns[{params.get('order[0][column]', '')}][data]", '')
    order_col = _SORTABLE.get(sort_key, 'total_qty')
    order_dir = 'ASC' if params.get('order[0][dir]') == 'asc' else 'DESC'
    with connection.cursor() as cursor:
        warehouses = [w['code'] for w in _warehouses(cursor)]
        cursor.execute(f'SELECT COUNT(DISTINCT w.sku) {_FROM} WHERE {where}', args)
        filtered = cursor.fetchone()[0]
        if args:
            cursor.execute('SELECT COUNT(DISTINCT sku) FROM dbo.WMS_INVENTORY')
            total = cursor.fetchone()[0]
        else:
            total = filtered

        order_sql = f"{order_col} {order_dir}{'' if order_col == 'sku' else ', sku'}"
        cursor.execute(
            _paged_sql(
                f"""
            SELECT w.sku, MAX(w.description) AS wms_name, MAX(w.uom) AS wms_uom,
                   SUM({_QTY}) AS total_qty, SUM({_AVAILABLE}) AS available_qty, SUM({_HELD}) AS held_qty
            {_FROM} WHERE {where} GROUP BY w.sku""",
                'a.total_qty, a.available_qty, a.held_qty',
                order_sql,
            ),
            [*args, start, length],
        )
        data = _rows(cursor)

        if data:
            codes = [r['sku'] for r in data]
            cursor.execute(
                f"SELECT w.sku, w._whseid, SUM({_QTY}) {_FROM} WHERE {where} AND w.sku IN ({', '.join(['%s'] * len(codes))}) GROUP BY w.sku, w._whseid",
                [*args, *codes],
            )
            split: dict[str, dict[str, Any]] = {}
            for sku, whs, qty in cursor.fetchall():
                split.setdefault(sku, {})[whs] = _num(qty)
            for row in data:
                row.update({code: split.get(row['sku'], {}).get(code) for code in warehouses})
    return {'draw': draw, 'recordsTotal': total, 'recordsFiltered': filtered, 'data': data, 'warehouses': warehouses}


def export_by_sku(params: Any) -> tuple[list[str], list[dict[str, Any]]]:
    where, args = _filters(params)
    with connection.cursor() as cursor:
        warehouses = [w['code'] for w in _warehouses(cursor)]
        cursor.execute(
            f'{_sku_agg(warehouses, where)} ORDER BY total_qty DESC, sku OFFSET 0 ROWS FETCH NEXT {EXPORT_MAX_ROWS} ROWS ONLY', args
        )
        return (warehouses, _rows(cursor))


@cached(*STOCK_SOURCES)
def get_top_sku(params: Any) -> dict[str, Any]:
    where, args = _filters(params)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            ;WITH a AS (SELECT TOP {TOP_LIMIT} w.sku, MAX(w.description) AS wms_name, MAX(w.uom) AS wms_uom, SUM({_QTY}) AS total_qty
                       {_FROM} WHERE {where} GROUP BY w.sku ORDER BY total_qty DESC, w.sku)
            SELECT a.sku AS sku, ISNULL(i.ItemName, a.wms_name) AS item_name, {_UOM} AS uom, a.total_qty
            FROM a LEFT JOIN dbo.SAP_ITEMS i ON i.ItemCode = a.sku {_UOM_JOIN} ORDER BY a.total_qty DESC, a.sku
            """,
            args,
        )
        top = _rows(cursor)
        if top:
            codes = [r['sku'] for r in top]
            cursor.execute(
                f"SELECT w.sku, w._whseid, SUM({_QTY}) {_FROM} WHERE {where} AND w.sku IN ({', '.join(['%s'] * len(codes))}) GROUP BY w.sku, w._whseid",
                [*args, *codes],
            )
            split: dict[str, dict[str, float]] = {}
            for sku, whs, qty in cursor.fetchall():
                split.setdefault(sku, {})[whs] = _num(qty)
            for row in top:
                row['by_warehouse'] = split.get(row['sku'], {})
    return {'data': top}


@cached(*STOCK_SOURCES)
def get_by_warehouse(params: Any) -> dict[str, Any]:
    where, args = _filters(params)
    with connection.cursor() as cursor:
        names = {w['code']: w['name'] for w in _warehouses(cursor)}
        cursor.execute(
            f'SELECT w._whseid AS code, SUM({_QTY}) AS total_qty, COUNT(DISTINCT w.sku) AS sku_count {_FROM} WHERE {where} GROUP BY w._whseid ORDER BY total_qty DESC',
            args,
        )
        data = _rows(cursor)
    for row in data:
        row['name'] = names.get(row['code'], row['code'])
    return {'data': data}


_LOCATION_SORTABLE = {'sku': 'sku', 'item_name': 'item_name', 'whs': 'whs', 'status': 'status', 'qty': 'qty'}


def _location_order(params: Any) -> str:
    sort_key = params.get(f"columns[{params.get('order[0][column]', '')}][data]", '') or params.get('sort', '')
    order_col = _LOCATION_SORTABLE.get(sort_key, 'sku')
    order_dir = 'DESC' if (params.get('order[0][dir]') or params.get('dir')) == 'desc' else 'ASC'
    return ', '.join([f'{order_col} {order_dir}', *(c for c in ('sku', 'whs', 'status') if c != order_col)])


def _paged_sql(agg_sql: str, cols: str, order_sql: str) -> str:
    if order_sql.startswith('item_name'):
        return f"""
            ;WITH a AS ({agg_sql})
            SELECT a.sku AS sku, ISNULL(i.ItemName, a.wms_name) AS item_name, {_UOM} AS uom, {cols}
            FROM a LEFT JOIN dbo.SAP_ITEMS i ON i.ItemCode = a.sku {_UOM_JOIN}
            ORDER BY {order_sql} OFFSET %s ROWS FETCH NEXT %s ROWS ONLY OPTION (HASH JOIN)
            """
    return f"""
        ;WITH a0 AS ({agg_sql}),
        a AS (SELECT * FROM a0 ORDER BY {order_sql} OFFSET %s ROWS FETCH NEXT %s ROWS ONLY)
        SELECT a.sku AS sku, ISNULL(i.ItemName, a.wms_name) AS item_name, {_UOM} AS uom, {cols}
        FROM a LEFT JOIN dbo.SAP_ITEMS i ON i.ItemCode = a.sku {_UOM_JOIN}
        ORDER BY {order_sql}
        """


def _location_sql(where: str, order_sql: str) -> str:
    return _paged_sql(
        f"""
        SELECT w.sku, w._whseid AS whs, ISNULL(w.status, '') AS status, MAX(w.description) AS wms_name,
               MAX(w.uom) AS wms_uom, SUM({_QTY}) AS qty
        {_FROM} WHERE {where} GROUP BY w.sku, w._whseid, w.status""",
        'a.whs AS whs, a.status AS status, a.qty',
        order_sql,
    )


@cached(*STOCK_SOURCES)
def get_by_location(params: Any) -> dict[str, Any]:

    where, args = _filters(params)
    try:
        start = max(0, int(params.get('start') or 0))
        length = min(MAX_PAGE_LENGTH, max(1, int(params.get('length') or 10)))
        draw = int(params.get('draw') or 0)
    except ValueError:
        start, length, draw = (0, 10, 0)
    order_sql = _location_order(params)
    with connection.cursor() as cursor:
        names = {w['code']: w['name'] for w in _warehouses(cursor)}
        cursor.execute(f'SELECT COUNT(*) FROM (SELECT 1 AS x {_FROM} WHERE {where} GROUP BY w.sku, w._whseid, w.status) t', args)
        filtered = cursor.fetchone()[0]
        if args:
            cursor.execute('SELECT COUNT(*) FROM (SELECT 1 AS x FROM dbo.WMS_INVENTORY GROUP BY sku, _whseid, status) t')
            total = cursor.fetchone()[0]
        else:
            total = filtered
        cursor.execute(_location_sql(where, order_sql), [*args, start, length])
        data = _rows(cursor)
    for row in data:
        row['whs_name'] = names.get(row['whs'], row['whs'])
    return {'draw': draw, 'recordsTotal': total, 'recordsFiltered': filtered, 'data': data}


def export_by_location(params: Any) -> list[dict[str, Any]]:

    where, args = _filters(params)
    with connection.cursor() as cursor:
        names = {w['code']: w['name'] for w in _warehouses(cursor)}
        cursor.execute(_location_sql(where, _location_order(params)), [*args, 0, EXPORT_MAX_ROWS])
        data = _rows(cursor)
    for row in data:
        row['whs_name'] = names.get(row['whs'], row['whs'])
    return data


@cached(*STOCK_SOURCES)
def get_by_group(params: Any) -> dict[str, Any]:
    where, args = _filters(params)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            ;WITH a AS (SELECT w.sku, SUM({_QTY}) AS total_qty {_FROM} WHERE {where} GROUP BY w.sku)
            SELECT ISNULL(i.ItemGroup1, '') AS code, ISNULL(MAX(g.ItmsGrpNam), N'Chưa phân nhóm') AS name, SUM(a.total_qty) AS total_qty
            FROM a LEFT JOIN dbo.SAP_ITEMS i ON i.ItemCode = a.sku LEFT JOIN dbo.SAP_ITEM_GROUPS g ON g.ItmsGrpCod = i.ItemGroup1
            GROUP BY i.ItemGroup1 ORDER BY total_qty DESC
            """,
            args,
        )
        data = _rows(cursor)
    return {'data': data}
