from __future__ import annotations
import sys
from pathlib import Path
import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
PROJECT_ROOT = Path('/opt/airflow/project')
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from services.pipeline.reconciliation import refresh_all_reconciliation_tables, refresh_inventory_reconciliation
LOCAL_TZ = 'Asia/Ho_Chi_Minh'
SQLSERVER_CONNECTION = 'sqlserver_tracking'

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
with DAG(dag_id='reconciliation_to_sqlserver', description='Refresh RECON_ECOM/RECON_DMS_DUYET/RECON_DMS_XUATKHO/RECON_WRT for the Data Tracking dashboard.', start_date=pendulum.datetime(2026, 9, 14, tz=LOCAL_TZ), schedule='0 7 * * *', catchup=False, max_active_runs=1, tags=['reconciliation', 'sqlserver', 'dashboard'], default_args={'retries': 2, 'retry_delay': pendulum.duration(minutes=2)}) as dag:
    PythonOperator(task_id='load_reconciliation_tables', python_callable=load_reconciliation_tables)
    PythonOperator(task_id='load_inventory_reconciliation', python_callable=load_inventory_reconciliation)
