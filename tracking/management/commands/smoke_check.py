"""Kiem tra hoi quy (golden master) cho toan bo trang/API/xuat Excel.

    python manage.py smoke_check --save /tmp/smoke_baseline.json      # chup ket qua goc
    python manage.py smoke_check --compare /tmp/smoke_baseline.json   # so sanh sau khi sua code

Goi moi URL theo ten route (reverse) voi tham so co dinh, dang nhap bang user superuser dau tien.
- Trang HTML: chi kiem tra HTTP 200 (giao dien duoc phep doi khi refactor).
- API JSON: so sanh toan bo noi dung.
- Excel: so sanh ten sheet + hash gia tri tung o.
Du lieu DB phai giu nguyen giua 2 lan chay (khong chay DAG o giua).
"""

from __future__ import annotations

import hashlib
import io
import json
import time
from typing import Any

import openpyxl
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import get_resolver, reverse

DATE_RANGE = {'date_from': '2026-09-01', 'date_to': '2026-09-30'}
DT_PAGE = {'draw': '1', 'start': '0', 'length': '10'}

PAGES = [
    'recon-ecom',
    'recon-dms-duyet',
    'recon-dms-xuatkho',
    'recon-wrt',
    'recon-inventory',
    'detail-ecom',
    'detail-dms-duyet',
    'detail-dms-xuatkho',
    'detail-wrt',
    'detail-employee-dms',
    'detail-employee-oms',
    'report-inventory',
    'report-ecom',
]
# route khong can kiem tra (khong phai tinh nang bao cao / kich hoat DAG Airflow that)
SKIPPED = {'login', 'logout', 'login-captcha', 'home', 'report-ecom-channels-refresh', 'report-ecom-channels-refresh-status'}
# Bang don hang sap mac dinh theo trang thai -> cac dong cung trang thai co the doi thu tu giua 2 lan goi.
# Neu khac baseline: van phai khop tong so dong / so dong sau loc / cau truc cot, chi canh bao.
UNSTABLE_ORDER = ('recon-', 'detail-')


def _relaxed(snap: dict[str, Any]) -> Any:
    body = snap.get('json')
    if not isinstance(body, dict) or 'data' not in body:
        return snap
    rows = body.get('data') or []
    return {
        'status': snap.get('status'),
        'recordsTotal': body.get('recordsTotal'),
        'recordsFiltered': body.get('recordsFiltered'),
        'rows': len(rows),
        'keys': sorted(rows[0].keys()) if rows else [],
    }


def _cases() -> list[tuple[str, dict[str, str]]]:
    cases: list[tuple[str, dict[str, str]]] = []
    for kind in ('ecom', 'dms-duyet', 'dms-xuatkho', 'wrt'):
        cases += [
            (f'recon-{kind}-report', {**DT_PAGE}),
            (f'recon-{kind}-report', {**DT_PAGE, 'status_sync': 'Not Sync', 'order[0][column]': '1', 'order[0][dir]': 'desc'}),
            (f'recon-{kind}-report', {**DT_PAGE, 'start': '20', **DATE_RANGE}),
            (f'recon-{kind}-export', {**DATE_RANGE}),
            (f'detail-{kind}-report', {**DT_PAGE, **DATE_RANGE}),
            (f'detail-{kind}-report', {**DT_PAGE, **DATE_RANGE, 'search[value]': 'JBL', 'order[0][column]': '1', 'order[0][dir]': 'asc'}),
            (f'detail-{kind}-export', {**DATE_RANGE}),
        ]
    cases += [
        ('recon-wrt-so-status-options', {}),
        ('detail-employee-dms-report', {**DT_PAGE, **DATE_RANGE}),
        ('detail-employee-dms-export', {**DATE_RANGE}),
        ('detail-employee-oms-report', {**DT_PAGE, **DATE_RANGE}),
        ('detail-employee-oms-export', {**DATE_RANGE}),
        ('recon-inventory-meta', {}),
        ('recon-inventory-report', {**DT_PAGE}),
        ('recon-inventory-report', {**DT_PAGE, 'status_sync': 'Lệch'}),
        ('recon-inventory-report', {**DT_PAGE, 'whs_code': 'W104', 'search[value]': 'tai nghe'}),
        ('recon-inventory-export', {'status_sync': 'Lệch'}),
        ('recon-inventory-diff-list', {}),
        ('recon-inventory-diff-export', {}),
        ('recon-inventory-detail', '__inventory_item__'),  # type: ignore[list-item]
        ('recon-inventory-detail-export', '__inventory_item__'),  # type: ignore[list-item]
        ('report-inventory-meta', {}),
    ]
    for f in ({}, {'whs': 'WH104'}, {'q': 'JBL', 'group': '100'}, {'status': 'ST05'}):
        cases += [
            ('report-inventory-kpi', f),
            ('report-inventory-top-sku', f),
            ('report-inventory-by-warehouse', f),
            ('report-inventory-by-group', f),
            (
                'report-inventory-by-sku',
                {**DT_PAGE, **f, 'order[0][column]': '3', 'order[0][dir]': 'desc', 'columns[3][data]': 'total_qty'},
            ),
        ]
    cases += [
        (
            'report-inventory-by-sku',
            {**DT_PAGE, 'start': '3190', 'order[0][column]': '1', 'order[0][dir]': 'asc', 'columns[1][data]': 'item_name'},
        ),
        ('report-inventory-by-sku', {**DT_PAGE, 'order[0][column]': '0', 'order[0][dir]': 'asc', 'columns[0][data]': 'sku'}),
        ('report-inventory-by-location', {**DT_PAGE, 'whs': 'WH104'}),
        (
            'report-inventory-by-location',
            {**DT_PAGE, 'q': 'I03127', 'order[0][column]': '5', 'order[0][dir]': 'desc', 'columns[5][data]': 'qty'},
        ),
        ('report-inventory-by-location', {**DT_PAGE, 'start': '9210'}),
        ('report-inventory-export', {'whs': 'WH104'}),
        ('report-inventory-by-location-export', {'whs': 'WH104', 'sort': 'qty', 'dir': 'desc'}),
        ('report-ecom-meta', {}),
    ]
    for f in (DATE_RANGE, {**DATE_RANGE, 'channel': 'SPE'}, {**DATE_RANGE, 'channel': 'TTS', 'shop': '7494711991440476753'}):
        cases += [(f'report-ecom-{area}', f) for area in ('kpi', 'daily', 'by-sale', 'top-products')]
        cases += [('report-ecom-orders', {**DT_PAGE, **f, 'order[0][column]': '0', 'order[0][dir]': 'desc'})]
    cases += [
        ('report-ecom-orders', {**DT_PAGE, **DATE_RANGE, 'start': '9990', 'status_group': 'cancel', 'search[value]': 'JBL'}),
        ('report-ecom-orders-export', {**DATE_RANGE, 'channel': 'LAZ'}),
    ]
    return cases


def _xlsx_summary(content: bytes) -> dict[str, Any]:
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
    sheets = {}
    for ws in wb.worksheets:
        rows = [[None if v is None else str(v) for v in row] for row in ws.iter_rows(values_only=True)]
        # bo qua thu tu dong (nhieu query xuat khong co ORDER BY) - chi so noi dung
        body = sorted(json.dumps(r, ensure_ascii=False) for r in rows[1:])
        sheets[ws.title] = {
            'rows': len(rows),
            'header': rows[0] if rows else [],
            'sha1': hashlib.sha1(json.dumps(body, ensure_ascii=False).encode('utf-8')).hexdigest(),
        }
    return {'sheets': sheets}


def _snapshot(response) -> dict[str, Any]:
    ctype = response.get('Content-Type', '')
    out: dict[str, Any] = {'status': response.status_code}
    if 'json' in ctype:
        body = response.json()
        if isinstance(body, dict):
            body.pop('draw', None)
        out['json'] = body
    elif 'spreadsheetml' in ctype:
        out['xlsx'] = _xlsx_summary(response.content)
        out['filename'] = response.get('Content-Disposition', '')
    return out


class Command(BaseCommand):
    help = 'Chup/so sanh ket qua moi trang, API, file Excel de kiem tra hoi quy khi refactor.'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--save', metavar='FILE')
        group.add_argument('--compare', metavar='FILE')

    def handle(self, *args, **opts):
        settings.ALLOWED_HOSTS = ['*']
        user = get_user_model().objects.filter(is_active=True, is_superuser=True).order_by('id').first()
        if not user:
            raise CommandError('Can 1 user superuser dang hoat dong de chay smoke_check.')
        client = Client()
        client.force_login(user)
        baseline = None
        if opts['compare']:
            with open(opts['compare'], encoding='utf-8') as f:
                baseline = json.load(f)

        results: dict[str, Any] = {}
        failures: list[str] = []
        warnings: list[str] = []
        t0 = time.time()

        for name in PAGES:
            r = client.get(reverse(name))
            key = f'PAGE {name}'
            results[key] = {'status': r.status_code}
            if r.status_code != 200:
                failures.append(f'{key}: HTTP {r.status_code}')

        r = client.get(reverse('home'))
        results['PAGE home'] = {'status': r.status_code, 'location': r.get('Location')}
        if r.status_code != 302 or r.get('Location') != reverse('recon-ecom'):
            failures.append(f'PAGE home: phai chuyen huong ve trang chu, nhan {r.status_code} {r.get("Location")}')

        # khoa = ten route + tham so (khong theo so thu tu -> them/bot truong hop khong lam lech baseline)
        def case_key(route: str, p: Any) -> str:
            return f'{route} {json.dumps(p, ensure_ascii=False, sort_keys=True)}'

        old_by_case: dict[str, Any] = {}
        for old_key, old in (baseline or {}).items():
            if not old_key.startswith('PAGE ') and isinstance(old, dict) and 'params' in old:
                route = old_key.split(' ', 1)[1] if old_key[:3].isdigit() else old_key.split(' ', 1)[0]
                old_by_case[case_key(route, old['params'])] = old
                old_by_case.setdefault(f'{route} __inventory_item__', old)

        for name, params in _cases():
            if params == '__inventory_item__':
                old = old_by_case.get(f'{name} __inventory_item__')
                if old:
                    params = old['params']
                else:
                    first = client.get(reverse('recon-inventory-report'), {**DT_PAGE, 'status_sync': 'Lệch'}).json()['data'][0]
                    params = {'item_code': first['item_code'], 'whs_code': first['whs_code'], 'status_item': first.get('status_item') or ''}
            key = case_key(name, params)
            r = client.get(reverse(name), params)
            snap = {'params': params, **_snapshot(r)}
            results[key] = snap
            if r.status_code != 200:
                failures.append(f'{key}: HTTP {r.status_code}')
            if baseline is not None:
                old = old_by_case.get(key)
                if old is None:
                    failures.append(f'{key}: khong co trong baseline')
                elif {k: v for k, v in old.items() if k != 'params'} != {k: v for k, v in snap.items() if k != 'params'}:
                    if name.startswith(UNSTABLE_ORDER) and name.endswith('-report') and _relaxed(old) == _relaxed(snap):
                        warnings.append(f'{key}: thu tu dong khac (so dong + cot van khop)')
                    else:
                        failures.append(f'{key}: KET QUA KHAC baseline (params={params})')

        covered = set(PAGES) | {n for n, _ in _cases()} | SKIPPED
        named = {n for n in get_resolver().reverse_dict if isinstance(n, str) and not n.startswith('admin')}
        missing = sorted(named - covered)
        if missing:
            self.stdout.write(self.style.WARNING(f'Route chua co trong smoke_check: {missing}'))

        if opts['save']:
            with open(opts['save'], 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=1, default=str)
            self.stdout.write(f'Da luu {len(results)} ket qua vao {opts["save"]} ({time.time() - t0:.0f}s)')
        for msg in warnings:
            self.stdout.write(self.style.WARNING(msg))
        for msg in failures:
            self.stdout.write(self.style.ERROR(msg))
        if failures:
            raise CommandError(f'{len(failures)} loi')
        self.stdout.write(self.style.SUCCESS(f'OK: {len(results)} trang/API/Excel ({time.time() - t0:.0f}s)'))
