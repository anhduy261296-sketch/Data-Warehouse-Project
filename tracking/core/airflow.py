from __future__ import annotations
import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..constants import AIRFLOW_API_PASSWORD, AIRFLOW_API_URL, AIRFLOW_API_USER

ACTIVE_STATES = ('queued', 'running')


class AirflowError(RuntimeError):
    pass


def _request(method: str, path: str, body: dict | None = None) -> dict[str, Any]:
    token = base64.b64encode(f'{AIRFLOW_API_USER}:{AIRFLOW_API_PASSWORD}'.encode()).decode()
    req = urllib.request.Request(
        f'{AIRFLOW_API_URL}{path}',
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization': f'Basic {token}', 'Content-Type': 'application/json', 'Accept': 'application/json'},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read() or b'{}')
    except urllib.error.HTTPError as exc:
        raise AirflowError(f'Airflow API {exc.code}: {exc.read()[:300].decode(errors="replace")}') from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise AirflowError(f'Khong ket noi duoc Airflow API: {exc}') from exc


def has_active_run(dag_id: str) -> bool:
    query = urllib.parse.urlencode([('state', s) for s in ACTIVE_STATES] + [('limit', 1)])
    return _request('GET', f'/dags/{dag_id}/dagRuns?{query}').get('total_entries', 0) > 0


def trigger_dag(dag_id: str, conf: dict | None = None) -> dict[str, Any]:
    return _request('POST', f'/dags/{dag_id}/dagRuns', {'conf': conf or {}})


def get_dag_run(dag_id: str, run_id: str) -> dict[str, Any]:
    return _request('GET', f'/dags/{dag_id}/dagRuns/{urllib.parse.quote(run_id, safe="")}')
