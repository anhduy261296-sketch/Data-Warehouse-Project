"""Cache ket qua bao cao theo PHIEN BAN DU LIEU - dung chung cho moi API bao cao / bang DataTables.

Moi API khai bao no doc tu NGUON nao (SOURCES). Phien ban 1 nguon = thoi diem pipeline nap nguon do gan nhat
(bang *_Load_Log / RECON_Refresh_Log). Khoa cache = ten + tham so + phien ban cac nguon:
  - DAG nap du lieu moi -> phien ban doi -> khoa doi -> tu lay du lieu moi (cham nhat VERSION_TTL giay), khong can xoa tay.
  - Phat hien phien ban moi -> xoa sach vung cache (giai phong RAM ngay, khong cho het TTL).
  - Tran RAM moi tien trinh ~= CACHES['reports'] MAX_ENTRIES x CACHE_MAX_ITEM_BYTES (ket qua lon hon thi khong cache).

    @cached('wms_inventory', 'sap_items')          # ham nhan params (request.GET) tra dict
    def get_kpi(params): ...

    cached_call('recon-ecom', ('recon',), lambda: run_detail_report(cfg, params), params)
"""

from __future__ import annotations

import functools
import hashlib
import json
import pickle
from typing import Any, Callable, Iterable

from django.core.cache import caches
from django.db import connection

from ..constants import REPORT_CACHE_MAX_ITEM_BYTES, REPORT_CACHE_TTL, REPORT_VERSION_TTL

cache = caches['reports']

# Nguon du lieu -> SQL tra 1 gia tri thay doi moi khi pipeline nap lai nguon do.
SOURCES: dict[str, str] = {
    'wms_inventory': "SELECT MAX(loaded_at) FROM dbo.WMS_INVENTORY_Load_Log WHERE status = 'SUCCESS'",
    'sap_items': 'SELECT MAX(LoadedAt) FROM dbo.SAP_ITEMS',
    'sap_item_groups': 'SELECT MAX(LoadedAt) FROM dbo.SAP_ITEM_GROUPS',
    'sap_uom': 'SELECT MAX(LoadedAt) FROM dbo.SAP_UOM',
    # DAG doi soat lam moi ca RECON_* lan STATUS_TRACKING (cot Status Sync cua bang chi tiet)
    'recon': 'SELECT MAX(refreshed_at) FROM dbo.RECON_Refresh_Log',
    'oms_orders': 'SELECT MAX(loaded_at) FROM dbo.OMS_ORDERS_Load_Log',
    'dms_so': 'SELECT MAX(loaded_at) FROM dbo.DMS_SO_Load_Log',
    'wrt_so': 'SELECT MAX(loaded_at) FROM dbo.WRT_SO_Load_Log',
}

# tham so khong anh huong ket qua: '_' (chong cache cua jQuery), 'draw' (so thu tu request cua DataTables)
_IGNORED_PARAMS = {'_', 'draw'}
_LAST_SEEN_KEY = 'reports:last_versions'


def _source_version(source: str) -> str:
    key = f'reports:version:{source}'
    version = cache.get(key)
    if version is None:
        with connection.cursor() as cursor:
            cursor.execute(SOURCES[source])
            version = str(cursor.fetchone()[0])
        last_seen = cache.get(_LAST_SEEN_KEY) or {}
        if source in last_seen and last_seen[source] != version:
            # du lieu moi -> bo het ket qua cu (cua moi nguon) de giai phong RAM; cac nguon khac tu doc lai version
            cache.clear()
            last_seen = {}
        cache.set(_LAST_SEEN_KEY, {**last_seen, source: version}, None)
        cache.set(key, version, REPORT_VERSION_TTL)
    return version


def _data_version(sources: Iterable[str]) -> str:
    return '|'.join(f'{s}={_source_version(s)}' for s in sources)


def cache_key(name: str, sources: Iterable[str], params: Any = None) -> str:
    params = params if params is not None else {}
    items = sorted((k, params.getlist(k) if hasattr(params, 'getlist') else [params[k]]) for k in params if k not in _IGNORED_PARAMS)
    raw = json.dumps([name, _data_version(sources), items], ensure_ascii=False, default=str)
    return 'reports:' + hashlib.sha1(raw.encode('utf-8')).hexdigest()


def get_or_set(key: str, producer: Callable[[], Any]) -> Any:
    result = cache.get(key)
    if result is None:
        result = producer()
        if len(pickle.dumps(result, pickle.HIGHEST_PROTOCOL)) <= REPORT_CACHE_MAX_ITEM_BYTES:
            cache.set(key, result, REPORT_CACHE_TTL)
    return result


def cached_call(name: str, sources: Iterable[str], producer: Callable[[], dict[str, Any]], params: Any = None) -> dict[str, Any]:
    """Lay ket qua tu cache (hoac tinh roi luu). DataTables: tra lai dung 'draw' cua request hien tai."""
    params = params if params is not None else {}
    result = get_or_set(cache_key(name, sources, params), producer)
    if isinstance(result, dict) and 'draw' in result and 'draw' in params:
        draw = str(params.get('draw') or '0')
        result = {**result, 'draw': int(draw) if draw.isdigit() else 0}
    return result


def cached(*sources: str):
    """Decorator cho ham bao cao fn(params) -> dict."""

    def decorator(fn):
        name = f'{fn.__module__}.{fn.__name__}'

        @functools.wraps(fn)
        def wrapper(params: Any = None) -> dict[str, Any]:
            params = params if params is not None else {}
            return cached_call(name, sources, lambda: fn(params), params)

        return wrapper

    return decorator
