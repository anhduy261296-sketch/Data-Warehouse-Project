"""Gọi API Incom Omni (SendMessage) để gửi ZNS và phân loại kết quả.

Chế độ dry_run (mặc định) không mở kết nối mạng: chỉ dựng payload và trả kết quả "Chạy thử".
"""

from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from ..constants import ZNS_ACCOUNTS, ZNS_API_TIMEOUT, ZNS_API_URL, ZNS_ROUTE_RULE, ZNS_SEND_MODE
from .values import MessagingError

RESPONSE_MAX_LEN = 2000
_MSG_ID_KEYS = ('idomnimess', 'msgid', 'msg_id', 'messageid', 'message_id')

# Loại lỗi của một lần gọi API.
KIND_TEMPORARY = 'temporary'  # chắc chắn / gần như chắc chắn chưa gửi: tự thử lại được
KIND_UNKNOWN = 'unknown'  # không biết tin đã đi chưa: không tự gửi lại
KIND_CONFIG = 'config'  # khách nào cũng lỗi: sai template, thiếu tham số, sai tài khoản
KIND_BUSINESS = 'business'  # Incom từ chối riêng khách này hoặc mã lỗi chưa phân loại

SUCCESS_STATUS = 1
CONFIG_STATUS_CODES = frozenset({-6, -2})  # -6: không có template, -2: thiếu tham số
_TEMPORARY_HTTP = frozenset({429, 503})
_UNKNOWN_HTTP = frozenset({500, 502, 504})
_CONFIG_HTTP = frozenset({401, 403, 404})
_MAYBE_SENT = 'Tin có thể đã được gửi.'


@dataclass
class SendResult:
    ok: bool
    simulated: bool = False
    kind: str | None = None
    http_status: int | None = None
    duration_ms: int | None = None
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


def mask_phone(phone: str | None) -> str:
    return f'{phone[:3]}****{phone[-3:]}' if phone and len(phone) > 6 else '***'


def _msg_id(body: Any) -> str | None:
    for node in (body, body.get('data') if isinstance(body, dict) else None):
        if isinstance(node, dict):
            for key, value in node.items():
                if key.lower() in _MSG_ID_KEYS and value not in (None, ''):
                    return str(value)[:100]
    return None


def _http_error(code: int, text: str) -> SendResult:
    response = text[:RESPONSE_MAX_LEN]
    if code in _TEMPORARY_HTTP:
        return SendResult(ok=False, kind=KIND_TEMPORARY, http_status=code, error=f'Incom tạm thời lỗi (HTTP {code}).', response=response)
    if code in _UNKNOWN_HTTP:
        return SendResult(ok=False, kind=KIND_UNKNOWN, http_status=code, error=f'Incom lỗi HTTP {code}. {_MAYBE_SENT}', response=response)
    if code in _CONFIG_HTTP:
        return SendResult(ok=False, kind=KIND_CONFIG, http_status=code, error=f'Sai cấu hình API hoặc tài khoản (HTTP {code}).', response=response)
    return SendResult(ok=False, kind=KIND_BUSINESS, http_status=code, error=f'Lỗi HTTP {code}.', response=response)


def _parse_success(code: int, text: str) -> SendResult:
    """HTTP 2xx: Incom báo kết quả trong body, vd. {"idOmniMess": "...", "status": "1", "code": "Success"}."""
    response = text[:RESPONSE_MAX_LEN]
    try:
        body = json.loads(text) if text else None
        status = int(str(body['status']).strip())
    except (ValueError, TypeError, KeyError):
        return SendResult(ok=False, kind=KIND_UNKNOWN, http_status=code, error=f'Không đọc được phản hồi của Incom. {_MAYBE_SENT}', response=response)
    message = body.get('code') or 'không rõ'
    if status == SUCCESS_STATUS:
        return SendResult(ok=True, http_status=code, msg_id=_msg_id(body), response=response)
    if status >= 0:
        return SendResult(ok=False, kind=KIND_UNKNOWN, http_status=code, error=f'Incom {status}: {message}. {_MAYBE_SENT}'[:1000], response=response)
    kind = KIND_CONFIG if status in CONFIG_STATUS_CODES else KIND_BUSINESS
    return SendResult(ok=False, kind=kind, http_status=code, error=f'Incom {status}: {message}'[:1000], response=response)


def _call(payload: dict[str, Any]) -> SendResult:
    req = urllib.request.Request(
        ZNS_API_URL,
        method='POST',
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
    )
    try:
        with urllib.request.urlopen(req, timeout=ZNS_API_TIMEOUT) as resp:
            return _parse_success(resp.status, resp.read().decode('utf-8', errors='replace'))
    except urllib.error.HTTPError as exc:
        return _http_error(exc.code, exc.read().decode('utf-8', errors='replace'))
    except urllib.error.URLError as exc:
        # urllib chỉ bọc URLError khi lỗi lúc kết nối / gửi yêu cầu: Incom chưa xử lý.
        return SendResult(ok=False, kind=KIND_TEMPORARY, error=f'Không kết nối được Incom: {exc.reason}'[:1000])
    except TimeoutError:
        return SendResult(ok=False, kind=KIND_UNKNOWN, error=f'Hết {ZNS_API_TIMEOUT} giây chờ, Incom không phản hồi. {_MAYBE_SENT}')
    except (http.client.HTTPException, OSError):
        return SendResult(ok=False, kind=KIND_UNKNOWN, error=f'Đứt kết nối sau khi đã gửi yêu cầu. {_MAYBE_SENT}')


def send(owner: str, phone: str, template_code: str, params: dict[str, str]) -> SendResult:
    if ZNS_SEND_MODE != 'live':
        return SendResult(ok=True, simulated=True, duration_ms=0, response='dry_run: không gọi API')
    started = time.monotonic()
    result = _call(build_payload(owner, phone, template_code, params))
    result.duration_ms = int((time.monotonic() - started) * 1000)
    return result
