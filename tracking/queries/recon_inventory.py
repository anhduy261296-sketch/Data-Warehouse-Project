from __future__ import annotations
import datetime
import time
from decimal import Decimal
from typing import Any
from django.db import connection
from ..constants import (
    INVENTORY_DETAIL_MAX_ROWS,
    INVENTORY_DIFF_STATUSES,
    INVENTORY_HIDDEN_STATUS,
    INVENTORY_STATUS_VALUES,
    SAP_DOC_DIRECTION,
    SAP_DOC_TYPE_CACHE_SEC,
    STATUS_CHANGE_LABEL,
    STATUS_CHANGE_MATCH_DAYS,
    STATUS_FREE_WAREHOUSES,
)
from ..core.datatables import DetailColumn, DetailReportConfig, _json_safe

INVENTORY_CONFIG = DetailReportConfig(
    table='dbo.RECON_INVENTORY',
    cache_sources=('recon',),
    where='1=1',
    status_values=INVENTORY_STATUS_VALUES,
    default_hidden_status=INVENTORY_HIDDEN_STATUS,
    default_order_sql="CASE t.StatusSync WHEN N'Lệch' THEN 0 WHEN N'Chỉ có SAP' THEN 1 WHEN N'Chỉ có WMS' THEN 2 WHEN N'Khớp' THEN 3 ELSE 4 END, ABS(t.DiffQty) DESC, t.ItemCode",
    filter_params=(('whs_code', 't.WhsCode'),),
    columns=[
        DetailColumn('t.StatusSync', 'status_sync', title='Status'),
        DetailColumn('t.ItemCode', 'item_code', searchable=True, title='ItemCode'),
        DetailColumn('t.ItemName', 'item_name', searchable=True, title='Tên hàng'),
        DetailColumn('t.WhsCode', 'whs_code', title='Kho'),
        DetailColumn('t.WhsName', 'whs_name', title='Tên kho'),
        DetailColumn('t.StatusItem', 'status_item', searchable=True, title='Trạng thái'),
        DetailColumn('t.SapQty', 'sap_qty', title='SAP tồn'),
        DetailColumn('t.WmsQty', 'wms_qty', title='WMS tồn'),
        DetailColumn('t.DiffQty', 'diff_qty', title='Chênh lệch'),
        DetailColumn('t.InvntryUom', 'uom', title='ĐVT'),
    ],
)


def get_inventory_meta() -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT (SELECT MAX(LoadedAt) FROM dbo.SAP_INVENTORY), (SELECT MAX(_scraped_at) FROM dbo.WMS_INVENTORY), (SELECT MAX(RefreshedAt) FROM dbo.RECON_INVENTORY)'
        )
        sap_at, wms_at, recon_at = cursor.fetchone()
        cursor.execute('SELECT DISTINCT WhsCode, WhsName FROM dbo.RECON_INVENTORY ORDER BY WhsCode')
        warehouses = [{'code': code, 'name': name} for code, name in cursor.fetchall()]
    return {
        'sap_snapshot_at': _json_safe(sap_at),
        'wms_snapshot_at': _json_safe(wms_at),
        'recon_refreshed_at': _json_safe(recon_at),
        'warehouses': warehouses,
        'statuses': list(INVENTORY_STATUS_VALUES),
        'summary': get_inventory_summary(),
    }


def get_inventory_summary() -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT ISNULL(SUM(SapQty), 0), ISNULL(SUM(WmsQty), 0) FROM dbo.RECON_INVENTORY WHERE StatusSync <> %s',
            [INVENTORY_CONFIG.default_hidden_status],
        )
        sap_total, wms_total = cursor.fetchone()
    diff = abs(sap_total - wms_total)
    ratio = diff / sap_total * 100 if sap_total else Decimal(0)
    return {
        'sap_total': _json_safe(sap_total),
        'wms_total': _json_safe(wms_total),
        'diff_total': _json_safe(diff),
        'diff_ratio_pct': _json_safe(ratio),
    }


def get_inventory_diff_list() -> dict[str, Any]:
    placeholders = ', '.join(('%s' for _ in INVENTORY_DIFF_STATUSES))
    with connection.cursor() as cursor:
        cursor.execute(
            f'''
            SELECT StatusSync, ItemCode, ItemName, WhsCode, StatusItem, SapQty, WmsQty, ABS(ISNULL(SapQty, 0) - ISNULL(WmsQty, 0)) AS Diff
            FROM dbo.RECON_INVENTORY
            WHERE StatusSync IN ({placeholders})
            ORDER BY Diff DESC, ItemCode, WhsCode, StatusItem
            ''',
            list(INVENTORY_DIFF_STATUSES),
        )
        rows = cursor.fetchall()
    groups = {status: [] for status in INVENTORY_DIFF_STATUSES}
    for status_sync, item_code, item_name, whs_code, status_item, sap_qty, wms_qty, diff in rows:
        groups[status_sync].append(
            {
                'item_code': item_code,
                'item_name': item_name,
                'whs_code': whs_code,
                'status_item': status_item,
                'sap_qty': _json_safe(sap_qty),
                'wms_qty': _json_safe(wms_qty),
                'diff_qty': _json_safe(diff),
            }
        )
    return {'both': groups['Lệch'], 'sap_only': groups['Chỉ có SAP'], 'wms_only': groups['Chỉ có WMS']}


def _status_after_dash(col: str) -> str:
    return f"CASE WHEN {col} IS NULL THEN '' WHEN CHARINDEX('-', {col}) = 0 THEN {col} ELSE RIGHT({col}, CHARINDEX('-', REVERSE({col})) - 1) END"


_DOC_TYPE_CACHE: dict[str, Any] = {'at': 0.0, 'names': {}, 'sales': set()}


def _sap_doc_types(cursor: Any) -> tuple[dict[str, str], set[str]]:
    now = time.monotonic()
    if not _DOC_TYPE_CACHE['names'] or now - _DOC_TYPE_CACHE['at'] > SAP_DOC_TYPE_CACHE_SEC:
        cursor.execute(
            'SELECT LoaiCT, MAX(TenLoaiCT), MAX(CASE WHEN DocType IN (15, 16) THEN 1 ELSE 0 END) FROM dbo.SAP_INOUT GROUP BY LoaiCT'
        )
        rows = cursor.fetchall()
        _DOC_TYPE_CACHE['names'] = {code: name for code, name, _ in rows}
        _DOC_TYPE_CACHE['sales'] = {code for code, _, is_sales in rows if is_sales}
        _DOC_TYPE_CACHE['at'] = now
    return _DOC_TYPE_CACHE['names'], _DOC_TYPE_CACHE['sales']


def _sap_doc_label(doc_type: int | None, type_name: str | None, in_whs: str | None, out_whs: str | None) -> str:
    if doc_type == 67:
        direction = 'Chuyển trạng thái' if in_whs and in_whs == out_whs else 'Chuyển kho'
    else:
        direction = SAP_DOC_DIRECTION.get(doc_type, 'Khác')
    return f'{direction} · {type_name}' if type_name else direction


def _wms_doc_label(src: str, code: str | None, names: dict[str, str], sales: set[str]) -> str:
    code = code or ''
    name = names.get(code) or names.get('GR' + code) or names.get('GI' + code) or code
    if src == 'I':
        direction = 'Hàng hoàn' if code in sales else 'Nhập'
    else:
        direction = 'Bán ra' if code in sales else 'Xuất'
    return f'{direction} · {name}' if name else direction


def _doc_key(doc_no: str | None) -> str:
    doc_no = (doc_no or '').strip()
    return doc_no[2:] if doc_no[:2] in ('I-', 'O-') else doc_no


def _group_docs(rows: list[tuple]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for doc_no, doc_date, doc_type, qty in rows:
        key = _doc_key(doc_no)
        doc = grouped.setdefault(key, {'doc_no': doc_no, 'doc_date': doc_date, 'doc_type': doc_type, 'qty': Decimal(0)})
        doc['qty'] += qty or 0
        if doc_date and (doc['doc_date'] is None or doc_date > doc['doc_date']):
            doc['doc_date'] = doc_date
    return {key: doc for key, doc in grouped.items() if doc['qty'] != 0}


def _wms_status_change_rows(cursor: Any, item_code: str, whs_code: str, wms_whse: str, status_item: str) -> list[tuple]:
    cursor.execute(
        f"""
        SELECT TOP {INVENTORY_DETAIL_MAX_ROWS} t.status, t.tostatus, t.trantype, t.sourcekey, t.tolpnid, DATEADD(hour, 7, t.adddate),
               CASE WHEN t.tostatus = %s THEN t.qty ELSE -t.qty END,
               (SELECT TOP 1 i.externreceiptkey FROM dbo.WMS_INBOUND i WHERE i.whseid = t.whseid AND i.lpnid = t.tolpnid)
        FROM dbo.WMS_TRANSACTION t
        WHERE t.sku = %s AND t.whseid = %s AND ISNULL(t.tostatus, '') <> '' AND t.status <> t.tostatus AND (t.status = %s OR t.tostatus = %s)
        ORDER BY t.adddate DESC
        """,
        [status_item, item_code, wms_whse, status_item, status_item],
    )
    rows = []
    for from_status, to_status, trantype, sourcekey, lpnid, doc_date, qty, receipt in cursor.fetchall():
        doc_no = f'{whs_code}_{receipt}' if receipt else (sourcekey or lpnid)
        rows.append((doc_no, doc_date, f'{STATUS_CHANGE_LABEL} · {from_status} → {to_status} ({trantype})', qty))
    return rows


def _pair_status_changes(sap_docs: dict[str, dict], wms_docs: dict[str, dict]) -> list[tuple[str, str]]:
    def is_change(doc: dict) -> bool:
        return (doc.get('doc_type') or '').startswith(STATUS_CHANGE_LABEL)

    sap_left = sorted(
        (k for k, d in sap_docs.items() if k not in wms_docs and is_change(d)),
        key=lambda k: sap_docs[k]['doc_date'] or datetime.datetime.min,
    )
    wms_left = [k for k, d in wms_docs.items() if k not in sap_docs and is_change(d)]
    pairs = []
    for sap_key in sap_left:
        sap = sap_docs[sap_key]
        if sap['doc_date'] is None:
            continue
        best, best_gap = None, None
        for wms_key in wms_left:
            wms = wms_docs[wms_key]
            if wms['qty'] != sap['qty'] or wms['doc_date'] is None:
                continue
            gap = abs((wms['doc_date'].date() - sap['doc_date'].date()).days)
            if gap <= STATUS_CHANGE_MATCH_DAYS and (best_gap is None or gap < best_gap):
                best, best_gap = wms_key, gap
        if best is not None:
            pairs.append((sap_key, best))
            wms_left.remove(best)
    return pairs


def _sort_by_date(docs: list[dict[str, Any]], key: str = 'doc_date') -> list[dict[str, Any]]:
    return sorted(docs, key=lambda d: (d[key] is not None, d[key] or datetime.datetime.min, d['doc_no'] or ''), reverse=True)


def get_inventory_detail(item_code: str, whs_code: str, status_item: str) -> dict[str, Any]:
    wms_whse = 'WH' + whs_code[1:] if whs_code.startswith('W') else whs_code
    status_free = whs_code in STATUS_FREE_WAREHOUSES
    if status_free:
        in_match, in_params = 't.IN_WhsCode = %s', [whs_code]
        out_match, out_params = 't.OUT_WhsCode = %s', [whs_code]
        wms_status_sql, wms_status_params = '', []
    else:
        in_match, in_params = f"(t.IN_WhsCode = %s AND {_status_after_dash('t.IN_BinCode')} = %s)", [whs_code, status_item]
        out_match, out_params = f"(t.OUT_WhsCode = %s AND {_status_after_dash('t.OUT_BinCode')} = %s)", [whs_code, status_item]
        wms_status_sql, wms_status_params = "AND ISNULL(t.conditioncode, '') = %s", [status_item]
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT TOP {INVENTORY_DETAIL_MAX_ROWS} t.SoCT_NhapXuat, t.DocDate_NhapXuat, t.DocType, t.TenLoaiCT, t.IN_WhsCode, t.OUT_WhsCode,
                   CASE WHEN {in_match} THEN t.InStock ELSE 0 END - CASE WHEN {out_match} THEN t.InStock ELSE 0 END
            FROM dbo.SAP_INOUT t
            WHERE t.ItemCode = %s AND ({in_match} OR {out_match})
            ORDER BY t.DocDate_NhapXuat DESC
            """,
            [*in_params, *out_params, item_code, *in_params, *out_params],
        )
        sap_rows = cursor.fetchall()
        cursor.execute(
            f"""
            SELECT TOP {INVENTORY_DETAIL_MAX_ROWS} doc_no, doc_date, src, doc_type, qty FROM (
                SELECT t.externreceiptkey AS doc_no, TRY_CONVERT(DATETIME2, ISNULL(t.datereceived, t.adddate)) AS doc_date, 'I' AS src, t.type AS doc_type,
                       TRY_CONVERT(DECIMAL(21,6), t.qtyreceivedpcs) AS qty
                FROM dbo.WMS_INBOUND t
                WHERE t.sku = %s AND t.whseid = %s {wms_status_sql} AND TRY_CONVERT(DECIMAL(21,6), t.qtyreceivedpcs) <> 0
                UNION ALL
                SELECT t.externorderkey, MAX(TRY_CONVERT(DATETIME2, ISNULL(t.actualshipdate, t.adddate))), 'O', MAX(t.type),
                       -MAX(TRY_CONVERT(DECIMAL(21,6), t.shippedqtypcs))
                FROM dbo.WMS_OUTBOUND t
                WHERE t.sku = %s AND t.whseid = %s {wms_status_sql} AND TRY_CONVERT(DECIMAL(21,6), t.shippedqtypcs) <> 0
                GROUP BY t.externorderkey, t.orderkey, t.orderlinenumber
            ) x
            ORDER BY doc_date DESC
            """,
            [item_code, wms_whse, *wms_status_params, item_code, wms_whse, *wms_status_params],
        )
        wms_rows = cursor.fetchall()
        names, sales = _sap_doc_types(cursor)
        change_rows = [] if status_free else _wms_status_change_rows(cursor, item_code, whs_code, wms_whse, status_item)
    sap_rows = [
        (doc_no, doc_date, _sap_doc_label(doc_type, type_name, in_whs, out_whs), qty)
        for doc_no, doc_date, doc_type, type_name, in_whs, out_whs, qty in sap_rows
    ]
    wms_rows = [
        (doc_no, doc_date, _wms_doc_label(src, code, names, sales), qty) for doc_no, doc_date, src, code, qty in wms_rows
    ] + change_rows
    sap_docs, wms_docs = _group_docs(sap_rows), _group_docs(wms_rows)
    matches = [(key, key) for key in sap_docs.keys() & wms_docs.keys()] + _pair_status_changes(sap_docs, wms_docs)
    both = []
    for sap_key, wms_key in matches:
        sap, wms = sap_docs[sap_key], wms_docs[wms_key]
        both.append(
            {
                'doc_no': sap_key,
                'wms_doc_no': wms['doc_no'] if wms_key != sap_key else None,
                'sap_date': sap['doc_date'],
                'wms_date': wms['doc_date'],
                'doc_date': sap['doc_date'] or wms['doc_date'],
                'doc_type': sap['doc_type'] or wms['doc_type'],
                'wms_doc_type': wms['doc_type'],
                'sap_qty': sap['qty'],
                'wms_qty': wms['qty'],
                'diff_qty': abs(sap['qty'] - wms['qty']),
            }
        )
    matched_sap = {k for k, _ in matches}
    matched_wms = {k for _, k in matches}
    sap_only = [doc for key, doc in sap_docs.items() if key not in matched_sap]
    wms_only = [doc for key, doc in wms_docs.items() if key not in matched_wms]
    result = {
        'both': _sort_by_date(both),
        'sap_only': _sort_by_date(sap_only),
        'wms_only': _sort_by_date(wms_only),
        'truncated': len(sap_rows) >= INVENTORY_DETAIL_MAX_ROWS or len(wms_rows) >= INVENTORY_DETAIL_MAX_ROWS,
    }
    for key in ('both', 'sap_only', 'wms_only'):
        result[key] = [{col: _json_safe(value) for col, value in doc.items()} for doc in result[key]]
    return result
