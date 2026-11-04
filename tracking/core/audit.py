from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from django.db import connection

DETAIL_MAX_LEN = 2000
# IP của request đang xử lý. Luồng gửi nền và lệnh quản trị không có request nên để trống.
client_ip: ContextVar[str | None] = ContextVar('audit_client_ip', default=None)

ACTION_LABELS = {
    'user.create': 'Tạo người dùng',
    'user.update': 'Sửa người dùng',
    'user.password': 'Đổi mật khẩu người dùng',
    'user.delete': 'Xóa người dùng',
    'role.create': 'Tạo nhóm người dùng',
    'role.update': 'Sửa nhóm người dùng',
    'role.delete': 'Xóa nhóm người dùng',
    'access.denied': 'Bị từ chối truy cập',
    'template.create': 'Tạo mẫu tin',
    'template.update': 'Sửa mẫu tin',
    'template.active': 'Bật / tắt mẫu tin',
    'template.delete': 'Xóa mẫu tin',
    'template.export': 'Xuất danh sách mẫu tin',
    'template.import': 'Nhập mẫu tin từ Excel',
    'template.approve': 'Duyệt mẫu tin',
    'template.reject': 'Từ chối mẫu tin',
    'zns.upload': 'Upload danh sách khách',
    'zns.confirm': 'Tạo và gửi lô',
    'zns.pause': 'Tự tạm dừng lô do lỗi',
    'zns.finish': 'Lô gửi xong',
    'zns.approve': 'Duyệt lô',
    'zns.reject': 'Từ chối lô',
    'zns.cancel': 'Hủy lô',
    'zns.skip': 'Bỏ qua khách lỗi',
    'zns.retry': 'Gửi lại trên lô',
    'zns.retry_new': 'Tạo lô gửi lại',
    'zns.resume': 'Tự chạy tiếp lô',
    'zns.stale_pause': 'Tạm dừng lô do việc gửi bị ngắt',
    'zns.export': 'Xuất khách của lô',
    'zns.export_history': 'Xuất lịch sử lô',
    'zns.log_export': 'Xuất nhật ký chiến dịch',
}
# Log thuộc menu Quản lý chiến dịch; còn lại (người dùng, nhóm, bị chặn quyền) thuộc Cấu hình.
CAMPAIGN_PREFIXES = ('template.', 'zns.')
CAMPAIGN_SQL = "(a.Action LIKE 'template.%%' OR a.Action LIKE 'zns.%%')"


def log(action: str, actor: str, target_type: str | None = None, target_id: Any = None, detail: str | None = None, department: int | None = None) -> None:
    with connection.cursor() as cursor:
        if department is None and target_type == 'batch' and target_id is not None:
            cursor.execute('SELECT DepartmentId FROM dbo.ZnsSendBatches WHERE Id = %s', [target_id])
            row = cursor.fetchone()
            department = row[0] if row else None
        cursor.execute(
            'INSERT INTO dbo.AppAuditLog (Action, Actor, TargetType, TargetId, Detail, IpAddress, DepartmentId) VALUES (%s, %s, %s, %s, %s, %s, %s)',
            [action, actor, target_type, None if target_id is None else str(target_id), detail[:DETAIL_MAX_LEN] if detail else None, client_ip.get(), department],
        )


def assign_batch_department(batch_id: int, department: int | None) -> None:
    """Log ghi trước khi lô có phòng ban (upload file) theo lô khi lô được xác nhận."""
    with connection.cursor() as cursor:
        cursor.execute("UPDATE dbo.AppAuditLog SET DepartmentId = %s WHERE TargetType = 'batch' AND TargetId = %s AND DepartmentId IS NULL", [department, str(batch_id)])
