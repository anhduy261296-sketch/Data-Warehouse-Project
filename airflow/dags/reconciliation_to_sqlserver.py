from __future__ import annotations
import sys
from pathlib import Path
from typing import Any
import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
from airflow.utils.trigger_rule import TriggerRule

PROJECT_ROOT = Path('/opt/airflow/project')
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from services.pipeline.data_quality import INVENTORY_SOURCES, ORDER_SOURCES, check_sources_ready, run_quality_checks
from services.pipeline.reconciliation import refresh_all_reconciliation_tables, refresh_inventory_reconciliation

LOCAL_TZ = 'Asia/Ho_Chi_Minh'
SQLSERVER_CONNECTION = 'sqlserver_tracking'
# Chờ nguồn trễ tối đa 1 giờ. Chạy tay khi biết nguồn chưa cập nhật thì truyền conf {"skip_freshness": true}.
SOURCE_WAIT_RETRIES = 6
SOURCE_WAIT_DELAY = pendulum.duration(minutes=10)


def wait_for_sources(sources: tuple[str, ...], **context: Any) -> None:
    if context['dag_run'].conf.get('skip_freshness'):
        print('Bo qua kiem tra nguon theo conf skip_freshness')
        return
    target_connection = MsSqlHook(mssql_conn_id=SQLSERVER_CONNECTION).get_conn()
    try:
        check_sources_ready(target_connection, sources)
    finally:
        target_connection.close()


def load_reconciliation_tables(**context: object) -> None:
    target_connection = MsSqlHook(mssql_conn_id=SQLSERVER_CONNECTION).get_conn()
    try:
        results = refresh_all_reconciliation_tables(target_connection)
    finally:
        target_connection.close()
    print(f'Reconciliation refresh completed: {results}')


def load_inventory_reconciliation(**context: object) -> None:
    target_connection = MsSqlHook(mssql_conn_id=SQLSERVER_CONNECTION).get_conn()
    try:
        row_count = refresh_inventory_reconciliation(target_connection)
    finally:
        target_connection.close()
    print(f'RECON_INVENTORY refresh completed: {row_count} rows')


def check_data_quality(**context: object) -> None:
    target_connection = MsSqlHook(mssql_conn_id=SQLSERVER_CONNECTION).get_conn()
    try:
        print(f'Data quality: {run_quality_checks(target_connection)}')
    finally:
        target_connection.close()


with DAG(
    dag_id='reconciliation_to_sqlserver',
    description='Refresh RECON_ECOM/RECON_DMS_DUYET/RECON_DMS_XUATKHO/RECON_WRT for the Data Tracking dashboard.',
    start_date=pendulum.datetime(2026, 9, 14, tz=LOCAL_TZ),
    schedule='0 7 * * *',
    catchup=False,
    max_active_runs=1,
    tags=['reconciliation', 'sqlserver', 'dashboard'],
    default_args={'retries': 2, 'retry_delay': pendulum.duration(minutes=2)},
) as dag:
    wait_orders = PythonOperator(
        task_id='wait_order_sources',
        python_callable=wait_for_sources,
        op_kwargs={'sources': ORDER_SOURCES},
        retries=SOURCE_WAIT_RETRIES,
        retry_delay=SOURCE_WAIT_DELAY,
    )
    wait_inventory = PythonOperator(
        task_id='wait_inventory_sources',
        python_callable=wait_for_sources,
        op_kwargs={'sources': INVENTORY_SOURCES},
        retries=SOURCE_WAIT_RETRIES,
        retry_delay=SOURCE_WAIT_DELAY,
    )
    load_orders = PythonOperator(task_id='load_reconciliation_tables', python_callable=load_reconciliation_tables)
    load_inventory = PythonOperator(task_id='load_inventory_reconciliation', python_callable=load_inventory_reconciliation)
    quality = PythonOperator(task_id='check_data_quality', python_callable=check_data_quality, retries=0, trigger_rule=TriggerRule.ALL_DONE)

    wait_orders >> load_orders >> quality
    wait_inventory >> load_inventory >> quality
