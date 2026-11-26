from __future__ import annotations
import sys
from pathlib import Path
import pendulum
from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

PROJECT_ROOT = Path('/opt/airflow/project')
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from services.pipeline.sap_item_groups import sync_sap_item_groups, sync_sap_uoms
from services.pipeline.sap_items import FULL_LOAD_START, last_success_to, sync_sap_items

LOCAL_TZ = 'Asia/Ho_Chi_Minh'
SQLSERVER_CONNECTION = 'sqlserver_tracking'
SAP_HANA_CONNECTION = 'sap_hana'
OVERLAP_DAYS = 1


def _window_from_context(target_connection: object, **context: object) -> tuple[str, str]:
    dag_run = context.get('dag_run')
    run_conf = getattr(dag_run, 'conf', None) or {}
    if run_conf.get('full'):
        return (FULL_LOAD_START, pendulum.now(LOCAL_TZ).format('YYYY-MM-DD HH:mm:ss'))
    from_date, to_date = (run_conf.get('from_date'), run_conf.get('to_date'))
    if bool(from_date) != bool(to_date):
        raise ValueError('Provide both from_date and to_date (yyyy-MM-dd HH:mm:ss), or full=true, or neither.')
    if from_date:
        return (str(from_date), str(to_date))
    now = pendulum.now(LOCAL_TZ).format('YYYY-MM-DD HH:mm:ss')
    last_to = last_success_to(target_connection)
    if not last_to:
        return (FULL_LOAD_START, now)
    start = pendulum.parse(last_to, tz=LOCAL_TZ).subtract(days=OVERLAP_DAYS).start_of('day')
    return (start.format('YYYY-MM-DD HH:mm:ss'), now)


def load_sap_items(**context: object) -> None:
    target_connection = MsSqlHook(mssql_conn_id=SQLSERVER_CONNECTION).get_conn()
    try:
        from_date, to_date = _window_from_context(target_connection, **context)
        row_count = sync_sap_items(target_connection, from_date=from_date, to_date=to_date)
    finally:
        target_connection.close()
    print(f'SAP Items -> SQL Server: {row_count} items, {from_date} to {to_date}.')


def load_sap_item_groups(**context: object) -> None:
    from hdbcli import dbapi

    conn = BaseHook.get_connection(SAP_HANA_CONNECTION)
    source_connection = dbapi.connect(address=conn.host, port=conn.port, user=conn.login, password=conn.password)
    target_connection = MsSqlHook(mssql_conn_id=SQLSERVER_CONNECTION).get_conn()
    try:
        row_count = sync_sap_item_groups(source_connection, target_connection)
        uom_count = sync_sap_uoms(source_connection, target_connection)
    finally:
        source_connection.close()
        target_connection.close()
    print(f'SAP item groups (OITB) -> SQL Server: {row_count} rows; UoM (OUOM): {uom_count} rows.')


with DAG(
    dag_id='sap_items_to_sqlserver_daily',
    description='Manual only: SAP item master (API /api/Items) -> dbo.SAP_ITEMS, item groups (HANA OITB) -> dbo.SAP_ITEM_GROUPS, UoM (HANA OUOM) -> dbo.SAP_UOM.',
    start_date=pendulum.datetime(2026, 10, 13, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=['sap', 'api', 'sqlserver', 'items', 'manual'],
    default_args={'retries': 2, 'retry_delay': pendulum.duration(minutes=5)},
) as dag:
    PythonOperator(task_id='load_sap_items', python_callable=load_sap_items) >> PythonOperator(
        task_id='load_sap_item_groups', python_callable=load_sap_item_groups
    )
