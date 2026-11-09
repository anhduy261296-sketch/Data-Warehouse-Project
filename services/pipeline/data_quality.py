"""Kiểm tra trước và sau bước đối soát: nguồn đã kéo xong chưa, dữ liệu sau khi load có bất thường không."""

from __future__ import annotations

import logging
from typing import Any, NamedTuple

from services.pipeline.alerts import send_telegram
from services.pipeline.common.constants import TARGET_SCHEMA

logger = logging.getLogger(__name__)

RESULTS_TABLE = 'DQ_Results'
REFRESH_LOG_TABLE = 'RECON_Refresh_Log'
ORDER_SOURCES = ('OMS_ORDERS', 'DMS_SO', 'WRT_SO', 'SAP_SO')
INVENTORY_SOURCES = ('SAP_INVENTORY', 'WMS_INVENTORY')
ORDER_RECON_TABLES = ('RECON_ECOM', 'RECON_DMS_DUYET', 'RECON_DMS_XUATKHO', 'RECON_WRT')
ALL_RECON_TABLES = (*ORDER_RECON_TABLES, 'RECON_INVENTORY')
# Số dòng đối soát tụt quá ngưỡng này so với lần trước thường là do nguồn kéo thiếu.
MIN_ROW_RATIO = 0.5
ERROR = 'error'
WARNING = 'warning'
# loaded_at lưu giờ UTC, còn lịch DAG theo ngày Việt Nam.
_START_OF_VN_DAY = 'DATEADD(HOUR, -7, CAST(CAST(DATEADD(HOUR, 7, SYSUTCDATETIME()) AS DATE) AS DATETIME2))'


class Check(NamedTuple):
    name: str
    severity: str
    sql: str
    detail: str


def _blank_key(table: str, column: str) -> Check:
    return Check(
        f'blank_key.{table}',
        ERROR,
        f"SELECT COUNT(*) FROM {TARGET_SCHEMA}.{table} WHERE {column} IS NULL OR {column} = ''",
        f'Dòng thiếu {column}',
    )


def _duplicate_key(table: str, columns: str) -> Check:
    return Check(
        f'duplicate_key.{table}',
        ERROR,
        f'SELECT COUNT(*) FROM (SELECT 1 AS x FROM {TARGET_SCHEMA}.{table} GROUP BY {columns} HAVING COUNT(*) > 1) d',
        f'Trùng khóa {columns}',
    )


CHECKS: tuple[Check, ...] = (
    _blank_key('OMS_ORDERS', 'order_number'),
    _blank_key('DMS_SO', 'OrderCode'),
    _blank_key('WRT_SO', 'order_number'),
    _blank_key('SAP_SO_All', 'U_SONo'),
    *(_duplicate_key(table, 'OrderCode') for table in ORDER_RECON_TABLES),
    _duplicate_key('RECON_INVENTORY', 'ItemCode, WhsCode, StatusItem'),
    Check(
        'bad_amount.OMS_ORDERS',
        ERROR,
        f'SELECT COUNT(*) FROM {TARGET_SCHEMA}.OMS_ORDERS WHERE total_amount_after_vat IS NOT NULL AND TRY_CONVERT(DECIMAL(18, 2), total_amount_after_vat) IS NULL',
        'Tiền không đổi được sang số',
    ),
    # DMS chỉ insert nên kéo tay chồng cửa sổ sẽ sinh dòng trùng; một đơn cũng có thể có hai dòng giống nhau thật nên chỉ cảnh báo.
    Check(
        'duplicate_lines.DMS_SO',
        WARNING,
        f'SELECT COUNT(*) FROM (SELECT 1 AS x FROM {TARGET_SCHEMA}.DMS_SO GROUP BY OrderCode, KeyOrder, ItemCode, Sku, SkuStatusCode, OrderType, Quantity, UnitPrice HAVING COUNT(*) > 1) d',
        'Nhóm dòng giống hệt nhau',
    ),
)


def check_sources_ready(target_conn: Any, sources: tuple[str, ...]) -> None:
    """Báo lỗi nếu nguồn chưa có lần kéo thành công trong ngày, để Airflow thử lại thay vì đối soát trên dữ liệu cũ."""
    cursor = target_conn.cursor()
    missing = []
    for source in sources:
        cursor.execute(f"SELECT COUNT(*) FROM {TARGET_SCHEMA}.{source}_Load_Log WHERE status = 'SUCCESS' AND loaded_at >= {_START_OF_VN_DAY}")
        if not cursor.fetchone()[0]:
            missing.append(source)
    if missing:
        raise RuntimeError(f"Chua keo xong trong ngay: {', '.join(missing)}")


def _row_drops(cursor: Any) -> list[str]:
    drops = []
    for table in ALL_RECON_TABLES:
        cursor.execute(f"SELECT TOP 2 row_count FROM {TARGET_SCHEMA}.{REFRESH_LOG_TABLE} WHERE table_name = %s AND status = 'SUCCESS' ORDER BY id DESC", (table,))
        counts = [row[0] for row in cursor.fetchall()]
        if len(counts) == 2 and counts[1] and counts[0] < counts[1] * MIN_ROW_RATIO:
            drops.append(f'{table}: {counts[1]} -> {counts[0]}')
    return drops


def _previous_violations(cursor: Any, name: str) -> int | None:
    cursor.execute(f'SELECT TOP 1 violations FROM {TARGET_SCHEMA}.{RESULTS_TABLE} WHERE check_name = %s ORDER BY id DESC', (name,))
    row = cursor.fetchone()
    return row[0] if row else None


def _record(cursor: Any, name: str, severity: str, violations: int, detail: str) -> None:
    status = 'PASS' if not violations else 'FAIL'
    cursor.execute(
        f'INSERT INTO {TARGET_SCHEMA}.{RESULTS_TABLE} (check_name, severity, violations, status, detail) VALUES (%s, %s, %s, %s, %s)',
        (name, severity, violations, status, detail[:400]),
    )


def run_quality_checks(target_conn: Any) -> dict[str, int]:
    """Chạy hết các kiểm tra, lưu vào DQ_Results rồi mới báo lỗi, để một lần chạy thấy đủ mọi vấn đề."""
    cursor = target_conn.cursor()
    results: dict[str, int] = {}
    errors = []
    changed_warnings = []
    for check in CHECKS:
        cursor.execute(check.sql)
        violations = cursor.fetchone()[0]
        results[check.name] = violations
        previous = _previous_violations(cursor, check.name)
        _record(cursor, check.name, check.severity, violations, check.detail)
        if violations and check.severity == ERROR:
            errors.append(f'{check.name}={violations}')
        elif violations:
            logger.warning('%s: %d (%s)', check.name, violations, check.detail)
            # Cảnh báo tồn tại lâu ngày chỉ báo khi số lượng đổi, tránh ngày nào cũng nhận cùng một tin.
            if violations != previous:
                changed_warnings.append(f'{check.name}: {previous or 0} -> {violations} ({check.detail})')
    drops = _row_drops(cursor)
    results['row_drop.RECON'] = len(drops)
    _record(cursor, 'row_drop.RECON', ERROR, len(drops), '; '.join(drops) or 'Số dòng đối soát ổn định')
    errors.extend(drops)
    target_conn.commit()
    if changed_warnings:
        send_telegram('🟡 Cảnh báo dữ liệu\n' + '\n'.join(changed_warnings))
    if errors:
        raise RuntimeError(f"Kiem tra du lieu khong dat: {'; '.join(errors)} (xem {RESULTS_TABLE})")
    return results
