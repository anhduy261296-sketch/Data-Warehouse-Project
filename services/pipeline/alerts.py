"""Gửi cảnh báo vận hành qua Telegram. Chưa cấu hình ALERT_TELEGRAM_* thì bỏ qua."""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

TELEGRAM_API = 'https://api.telegram.org'
REQUEST_TIMEOUT_SECONDS = 10
MAX_MESSAGE_LENGTH = 3500
MAX_ERROR_LENGTH = 500
VN_TZ = timezone(timedelta(hours=7))
# Nội dung lỗi có thể chứa thông tin đăng nhập, không được gửi ra dịch vụ ngoài.
_SECRET_PATTERNS = (
    re.compile(r'(?i)\b(password|passwd|pwd|token|refresh_token|access_token|client_secret|secret|api[_-]?key|authorization)\b(["\']?\s*[:=]\s*["\']?)(bearer\s+)?[^\s,;&"\'}]+'),
    re.compile(r'(?i)\bbearer\s+[\w.~+/=-]+'),
    re.compile(r'://[^/\s:@]+:[^/\s@]+@'),
)


def redact(text: Any) -> str:
    result = str(text)
    result = _SECRET_PATTERNS[0].sub(r'\1\2***', result)
    result = _SECRET_PATTERNS[1].sub('Bearer ***', result)
    return _SECRET_PATTERNS[2].sub('://***@', result)


def send_telegram(message: str) -> bool:
    """Không bao giờ raise: lỗi gửi cảnh báo không được làm hỏng task đang chạy."""
    token = os.environ.get('ALERT_TELEGRAM_TOKEN', '').strip()
    chat_id = os.environ.get('ALERT_TELEGRAM_CHAT_ID', '').strip()
    if not token or not chat_id:
        return False
    body = json.dumps({'chat_id': chat_id, 'text': message[:MAX_MESSAGE_LENGTH], 'disable_web_page_preview': True}).encode('utf-8')
    request = urllib.request.Request(f'{TELEGRAM_API}/bot{token}/sendMessage', data=body, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.status == 200
    except Exception as exc:
        # Không log exc nguyên bản vì URL chứa token.
        logger.warning('Gui canh bao Telegram that bai: %s', type(exc).__name__)
        return False


def notify_task_failure(context: dict[str, Any]) -> None:
    """on_failure_callback của Airflow: chỉ chạy khi task đã hết lượt thử lại."""
    try:
        instance = context['task_instance']
        now = datetime.now(VN_TZ).strftime('%d/%m/%Y %H:%M')
        error = redact(context.get('exception'))[:MAX_ERROR_LENGTH]
        send_telegram(f'🔴 DAG lỗi\nDAG: {instance.dag_id}\nTask: {instance.task_id}\nLúc: {now}\nLỗi: {error}')
    except Exception as exc:
        logger.warning('Khong tao duoc canh bao: %s', type(exc).__name__)
