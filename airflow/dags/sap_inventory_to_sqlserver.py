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
from services.pipeline.sap_inventory import START_DATE, sync_sap_inventory
LOCAL_TZ = 'Asia/Ho_Chi_Minh'
SAP_HANA_CONNECTION = 'sap_hana'
SQLSERVER_CONNECTION = 'sqlserver_tracking'

def _get_sap_hana_conn():
    from hdbcli import dbapi
    conn = BaseHook.get_connection(SAP_HANA_CONNECTION)
    return dbapi.connect(address=conn.host, port=conn.port, user=conn.login, password=conn.password)

def _window_from_context(**context: object) -> tuple[str, str, bool]:
    dag_run = context.get('dag_run')
    run_conf = getattr(dag_run, 'conf', None) or {}
    start_date = str(run_conf.get('start_date') or START_DATE)
    end_date = run_conf.get('end_date')
    if not end_date:
        interval_end = pendulum.instance(context['data_interval_end']).in_timezone(LOCAL_TZ)
        end_date = interval_end.subtract(days=1).format('YYYY-MM-DD')
    return (start_date, str(end_date), bool(run_conf.get('force', False)))

def load_sap_inventory(**context: object) -> None:
    start_date, end_date, force = _window_from_context(**context)
    source_connection = _get_sap_hana_conn()
    target_connection = MsSqlHook(mssql_conn_id=SQLSERVER_CONNECTION).get_conn()
    try:
        row_count = sync_sap_inventory(source_connection, target_connection, start_date=start_date, end_date=end_date, force=force)
    finally:
        source_connection.close()
        target_connection.close()
    print(f'SAP inventory -> SQL Server: {row_count} rows, {start_date} to {end_date}.')
with DAG(dag_id='sap_inventory_to_sqlserver_daily', description='Full-refresh SAP inventory movements (BTS_RPT_R502_KT) from 2026-06-28 to D-1 into dbo.SAP_INVENTORY.', start_date=pendulum.datetime(2026, 10, 6, tz=LOCAL_TZ), schedule='0 6 * * *', catchup=False, max_active_runs=1, tags=['sap', 'hana', 'sqlserver', 'inventory'], default_args={'retries': 2, 'retry_delay': pendulum.duration(minutes=10)}) as dag:
    PythonOperator(task_id='load_sap_inventory', python_callable=load_sap_inventory)
