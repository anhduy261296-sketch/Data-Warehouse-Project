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
from services.pipeline.wms_transaction import sync_wms_transaction
LOCAL_TZ = 'Asia/Ho_Chi_Minh'
SQLSERVER_CONNECTION = 'sqlserver_tracking'
LOOKBACK_DAYS = 2

def _window_from_context(**context: object) -> tuple[str, str]:
    dag_run = context.get('dag_run')
    run_conf = getattr(dag_run, 'conf', None) or {}
    start_date = run_conf.get('start_date')
    end_date = run_conf.get('end_date')
    if bool(start_date) != bool(end_date):
        raise ValueError('Provide both start_date and end_date (YYYY-MM-DD), or neither.')
    if start_date:
        return (str(start_date)[:10], str(end_date)[:10])
    interval_end = pendulum.instance(context['data_interval_end']).in_timezone(LOCAL_TZ)
    source_day = interval_end.subtract(days=1)
    return (source_day.subtract(days=LOOKBACK_DAYS - 1).format('YYYY-MM-DD'), source_day.format('YYYY-MM-DD'))

def load_wms_transaction(**context: object) -> None:
    start_date, end_date = _window_from_context(**context)
    target_connection = MsSqlHook(mssql_conn_id=SQLSERVER_CONNECTION).get_conn()
    try:
        row_count = sync_wms_transaction(target_connection, start_date=start_date, end_date=end_date)
    finally:
        target_connection.close()
    print(f'WMS Transaction -> SQL Server: {row_count} rows, {start_date} to {end_date}.')
with DAG(dag_id='wms_transaction_to_sqlserver_daily', description='Replace-by-day WMS Smartlog inventory transactions (ITRN) into dbo.WMS_TRANSACTION (SQL Server).', start_date=pendulum.datetime(2026, 10, 10, tz=LOCAL_TZ), schedule='30 3 * * *', catchup=False, max_active_runs=1, tags=['wms', 'sqlserver', 'transaction'], default_args={'retries': 2, 'retry_delay': pendulum.duration(minutes=5)}) as dag:
    PythonOperator(task_id='load_wms_transaction', python_callable=load_wms_transaction)
