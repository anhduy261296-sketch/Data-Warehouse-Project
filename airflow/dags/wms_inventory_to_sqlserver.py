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
from services.pipeline.wms_inventory import sync_wms_inventory
LOCAL_TZ = 'Asia/Ho_Chi_Minh'
SQLSERVER_CONNECTION = 'sqlserver_tracking'

def load_wms_inventory(**context: object) -> None:
    target_connection = MsSqlHook(mssql_conn_id=SQLSERVER_CONNECTION).get_conn()
    try:
        row_count = sync_wms_inventory(target_connection)
    finally:
        target_connection.close()
    print(f'WMS Inventory -> SQL Server full-refresh completed: {row_count} rows.')
with DAG(dag_id='wms_inventory_to_sqlserver_daily', description='Full-refresh (per-kho) WMS Smartlog Inventory snapshot into dbo.WMS_INVENTORY (SQL Server).', start_date=pendulum.datetime(2026, 9, 28, tz=LOCAL_TZ), schedule='0 5 * * *', catchup=False, max_active_runs=1, tags=['wms', 'sqlserver', 'inventory'], default_args={'retries': 2, 'retry_delay': pendulum.duration(minutes=5)}) as dag:
    PythonOperator(task_id='load_wms_inventory', python_callable=load_wms_inventory)
