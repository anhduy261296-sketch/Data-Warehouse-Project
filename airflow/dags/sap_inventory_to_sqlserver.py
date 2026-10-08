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
from services.pipeline.sap_inventory import sync_sap_inventory
LOCAL_TZ = 'Asia/Ho_Chi_Minh'
SAP_HANA_CONNECTION = 'sap_hana'
SQLSERVER_CONNECTION = 'sqlserver_tracking'

def _get_sap_hana_conn():
    from hdbcli import dbapi
    conn = BaseHook.get_connection(SAP_HANA_CONNECTION)
    return dbapi.connect(address=conn.host, port=conn.port, user=conn.login, password=conn.password)

def load_sap_inventory(**context: object) -> None:
    dag_run = context.get('dag_run')
    run_conf = getattr(dag_run, 'conf', None) or {}
    source_connection = _get_sap_hana_conn()
    target_connection = MsSqlHook(mssql_conn_id=SQLSERVER_CONNECTION).get_conn()
    try:
        row_count = sync_sap_inventory(source_connection, target_connection, force=bool(run_conf.get('force', False)))
    finally:
        source_connection.close()
        target_connection.close()
    print(f'SAP stock on hand (OITW) -> SQL Server: {row_count} rows.')
with DAG(dag_id='sap_inventory_to_sqlserver_daily', description='Snapshot SAP stock on hand (OITW, OnHand <> 0) into dbo.SAP_INVENTORY.', start_date=pendulum.datetime(2026, 10, 7, tz=LOCAL_TZ), schedule='0 5 * * *', catchup=False, max_active_runs=1, tags=['sap', 'hana', 'sqlserver', 'inventory'], default_args={'retries': 2, 'retry_delay': pendulum.duration(minutes=10)}) as dag:
    PythonOperator(task_id='load_sap_inventory', python_callable=load_sap_inventory)
