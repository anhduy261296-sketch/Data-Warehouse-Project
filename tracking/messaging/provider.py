"""Gọi API Incom Omni (SendMessage) để gửi ZNS.

Chế độ dry_run (mặc định) không mở kết nối mạng: chỉ dựng payload và trả kết quả "Chạy thử".
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from ..constants import ZNS_ACCOUNTS, ZNS_API_TIMEOUT, ZNS_API_URL, ZNS_ROUTE_RULE, ZNS_SEND_MODE
from .values import MessagingError

logger = logging.getLogger(__name__)
RESPONSE_MAX_LEN = 2000
_MSG_ID_KEYS = ('idomnimess', 'msgid', 'msg_id', 'messageid', 'message_id')


@dataclass
class SendResult:
    ok: bool
    simulated: bool = False
    msg_id: str | None = None
    error: str | None = None
    response: str | None = None


def send_mode() -> str:
    return ZNS_SEND_MODE


def check_account(owner: str) -> None:
    """Chế độ live bắt buộc có tài khoản của chủ hàng; dry_run thì không cần."""
    if ZNS_SEND_MODE != 'live':
        return
    username, password = ZNS_ACCOUNTS.get(owner) or ('', '')
    if not username or not password:
        raise MessagingError(f'Chưa cấu hình tài khoản Incom cho {owner} (ZNS_{owner}_USERNAME / ZNS_{owner}_PASSWORD trong .env).')


def build_payload(owner: str, phone: str, template_code: str, params: dict[str, str]) -> dict[str, Any]:
    username, password = ZNS_ACCOUNTS.get(owner) or ('', '')
    return {
        'username': username,
        'password': password,
        'phonenumber': phone,
        'routerule': ZNS_ROUTE_RULE,
        'templatecode': template_code,
        'list_param': params,
    }


def masked(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, 'password': '***' if payload.get('password') else ''}


def _msg_id(body: Any) -> str | None:
    for node in (body, body.get('data') if isinstance(body, dict) else None):
        if isinstance(node, dict):
            for key, value in node.items():
                if key.lower() in _MSG_ID_KEYS and value not in (None, ''):
                    return str(value)[:100]
    return None


def send(owner: str, phone: str, template_code: str, params: dict[str, str]) -> SendResult:
    payload = build_payload(owner, phone, template_code, params)
    if ZNS_SEND_MODE != 'live':
        logger.info('ZNS dry_run %s', json.dumps(masked(payload), ensure_ascii=False))
        return SendResult(ok=True, simulated=True, response='dry_run: không gọi API')

    req = urllib.request.Request(
        ZNS_API_URL,
        method='POST',
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
    )
    try:
        with urllib.request.urlopen(req, timeout=ZNS_API_TIMEOUT) as resp:
            text = resp.read().decode('utf-8', errors='replace')
            code = resp.status
    except urllib.error.HTTPError as exc:
        text = exc.read().decode('utf-8', errors='replace')
        return SendResult(ok=False, error=f'Lỗi HTTP {exc.code}', response=text[:RESPONSE_MAX_LEN])
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return SendResult(ok=False, error=f'Lỗi kết nối: {exc}'[:500])

    try:
        body = json.loads(text) if text else None
    except ValueError:
        body = None
    if not 200 <= code < 300:
        return SendResult(ok=False, error=f'Lỗi HTTP {code}', response=text[:RESPONSE_MAX_LEN])
    # Incom trả HTTP 200 cả khi lỗi nghiệp vụ, vd. {"idOmniMess": null, "status": "-6", "code": "Can't find template ..."}:
    # status âm = lỗi.
    error = _business_error(body)
    if error:
        return SendResult(ok=False, error=error[:1000], response=text[:RESPONSE_MAX_LEN])
    return SendResult(ok=True, msg_id=_msg_id(body), response=text[:RESPONSE_MAX_LEN])


def _business_error(body: Any) -> str | None:
    if not isinstance(body, dict) or body.get('status') is None:
        return None
    try:
        status = int(str(body['status']).strip())
    except ValueError:
        return None
    if status >= 0:
        return None
    return f'Incom {status}: {body.get("code") or "lỗi không rõ"}'
