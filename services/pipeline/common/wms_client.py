from __future__ import annotations

import logging
import os
import time
from typing import Callable, TypeVar

import requests

logger = logging.getLogger(__name__)
T = TypeVar('T')

WMS_LOGIN_URL = os.environ.get('WMS_LOGIN_URL', 'https://authentication.smartlog.info/api/User/login')
WMS_USERNAME = os.environ.get('WMS_USERNAME', '')
WMS_PASSWORD = os.environ.get('WMS_PASSWORD', '')
WMS_STORERKEY = os.environ.get('WMS_STORERKEY', 'PGI')

MAX_FETCH_RETRIES = 3
FETCH_RETRY_DELAY_SEC = 3
BUSY_MAX_RETRIES = 5
BUSY_RETRY_DELAY_SEC = 20
MAX_RELOGINS = 3
RELOGIN_DELAY_SEC = 5
REQUEST_DELAY_SEC = 1.0

_TOKEN_CACHE: dict[str, str] = {}


def login() -> str:
    if not WMS_USERNAME or not WMS_PASSWORD:
        raise RuntimeError('Chua cau hinh WMS_USERNAME/WMS_PASSWORD (.env) - can dien truoc khi chay DAG.')
    response = requests.post(WMS_LOGIN_URL, json={'username': WMS_USERNAME, 'password': WMS_PASSWORD}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    token = payload.get('token')
    if not token:
        raise RuntimeError(f"Login WMS khong tra ve 'token': {str(payload)[:300]}")
    return token


def start_session() -> str:
    token = login()
    _TOKEN_CACHE['token'] = token
    return token


def _is_server_busy(response: requests.Response | None) -> bool:
    return response is not None and 'server is busy' in response.text.lower()


def call_with_retry(request_once: Callable[[str], T], token: str, label: str) -> T:
    busy_retries = 0
    other_retries = 0
    relogins = 0
    while True:
        try:
            return request_once(_TOKEN_CACHE.get('token') or token)
        except requests.exceptions.RequestException as exc:
            response = getattr(exc, 'response', None)
            status = response.status_code if response is not None else None
            if status == 401 and relogins < MAX_RELOGINS:
                relogins += 1
                logger.warning(
                    '%s: token bi tu choi (401) - dang nhap lai (lan %d/%d). Neu lap lai lien tuc, kiem tra co noi khac '
                    'dang dang nhap cung tai khoan WMS khong.',
                    label,
                    relogins,
                    MAX_RELOGINS,
                )
                time.sleep(RELOGIN_DELAY_SEC * relogins)
                _TOKEN_CACHE['token'] = login()
                continue
            if _is_server_busy(response):
                busy_retries += 1
                if busy_retries > BUSY_MAX_RETRIES:
                    raise
                logger.warning('%s: server bao busy (lan %d/%d), cho %ds.', label, busy_retries, BUSY_MAX_RETRIES, BUSY_RETRY_DELAY_SEC)
                time.sleep(BUSY_RETRY_DELAY_SEC)
                continue
            other_retries += 1
            if other_retries > MAX_FETCH_RETRIES:
                raise
            logger.warning(
                '%s: %s (lan %d/%d), thu lai sau %ds.',
                label,
                status or type(exc).__name__,
                other_retries,
                MAX_FETCH_RETRIES,
                FETCH_RETRY_DELAY_SEC,
            )
            time.sleep(FETCH_RETRY_DELAY_SEC)
