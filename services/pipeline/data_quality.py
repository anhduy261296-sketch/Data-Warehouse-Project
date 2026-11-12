"""Kiểm tra trước và sau bước đối soát: nguồn đã kéo xong chưa, dữ liệu sau khi load có bất thường không."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, NamedTuple

from services.pipeline.alerts import VN_TZ, send_telegram
from services.pipeline.common.constants import TARGET_SCHEMA
from services.pipeline.dms_sales_orders import SOURCE_QUERY as DMS_SOURCE_QUERY

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
)
# Không kiểm tra dòng giống hệt trong DMS_SO: DMS cho nhập mỗi chiếc một dòng (S45457 có 104 dòng giống nhau thật),
# và bảng không có mã dòng gốc. Thay bằng so số dòng với nguồn theo ngày tạo.
DMS_GAP_CHECK = 'row_gap.DMS_SO'
# Rộng hơn RELOAD_DAYS của DAG DMS để thấy cả báo giá được xác nhận sau khi đã ra khỏi khung nạp lại.
DMS_COMPARE_DAYS = 14


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


def dms_row_gaps(source_conn: Any, target_conn: Any, today: date | None = None) -> list[str]:
    """So số dòng DMS nguồn và DMS_SO theo ngày tạo, các ngày trước hôm nay (hôm nay DAG DMS chưa kéo)."""
    end_day = today or datetime.now(VN_TZ).date()
    window = {'start_at': f'{end_day - timedelta(days=DMS_COMPARE_DAYS)} 00:00:00', 'end_at': f'{end_day} 00:00:00'}
    source_cursor = source_conn.cursor()
    source_cursor.execute(f'SELECT CAST(q."CreateDate" AS DATE)::text, COUNT(*) FROM ({DMS_SOURCE_QUERY}) q GROUP BY 1', window)
    source = {day: count for day, count in source_cursor.fetchall()}
    target_cursor = target_conn.cursor()
    target_cursor.execute(
        f'SELECT CONVERT(VARCHAR(10), CAST(CreateDate AS DATE), 23), COUNT(*) FROM {TARGET_SCHEMA}.DMS_SO '
        'WHERE CreateDate >= %s AND CreateDate < %s GROUP BY CAST(CreateDate AS DATE)',
        (window['start_at'], window['end_at']),
    )
    target = {day: count for day, count in target_cursor.fetchall()}
    return [f'{day}: nguồn {source.get(day, 0)}, server {target.get(day, 0)}' for day in sorted(source.keys() | target.keys()) if source.get(day, 0) != target.get(day, 0)]


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


def run_quality_checks(target_conn: Any, dms_conn: Any = None) -> dict[str, int]:
    """Chạy hết các kiểm tra, lưu vào DQ_Results rồi mới báo lỗi, để một lần chạy thấy đủ mọi vấn đề."""
    cursor = target_conn.cursor()
    results: dict[str, int] = {}
    errors = []
    changed_warnings = []

    def warn(name: str, violations: int, detail: str) -> None:
        previous = _previous_violations(cursor, name)
        _record(cursor, name, WARNING, violations, detail)
        if not violations:
            return
        logger.warning('%s: %d (%s)', name, violations, detail)
        # Cảnh báo tồn tại lâu ngày chỉ báo khi số lượng đổi, tránh ngày nào cũng nhận cùng một tin.
        if violations != previous:
            before = 'chưa có' if previous is None else previous
            changed_warnings.append(f'{name}: {before} -> {violations} ({detail})')

    for check in CHECKS:
        cursor.execute(check.sql)
        violations = cursor.fetchone()[0]
        results[check.name] = violations
        if check.severity == WARNING:
            warn(check.name, violations, check.detail)
            continue
        _record(cursor, check.name, check.severity, violations, check.detail)
        if violations:
            errors.append(f'{check.name}={violations}')
    if dms_conn is not None:
        try:
            gaps = dms_row_gaps(dms_conn, target_conn)
        except Exception as exc:
            errors.append(f'{DMS_GAP_CHECK}: khong doc duoc DMS ({type(exc).__name__})')
        else:
            results[DMS_GAP_CHECK] = len(gaps)
            # Đơn chưa chốt được nạp lại lúc 00:00 nên có thể lệch nhẹ nếu DMS sửa đơn sau giờ đó; để mức cảnh báo.
            warn(DMS_GAP_CHECK, len(gaps), '; '.join(gaps) or f'Khớp nguồn {DMS_COMPARE_DAYS} ngày gần nhất')
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
