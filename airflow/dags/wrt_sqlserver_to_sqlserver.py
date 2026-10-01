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
from services.pipeline.wrt_sales import sync_wrt_sales
LOCAL_TZ = 'Asia/Ho_Chi_Minh'
WRT_SQLSERVER_CONNECTION = 'wrt_sqlserver'
SQLSERVER_CONNECTION = 'sqlserver_tracking'

def _window_from_context(**context: object) -> tuple[str, str]:
    dag_run = context.get('dag_run')
    run_conf = getattr(dag_run, 'conf', None) or {}
    start_at = run_conf.get('start_at')
    end_at = run_conf.get('end_at')
    if bool(start_at) != bool(end_at):
        raise ValueError('Provide both start_at and end_at, or neither.')
    if start_at:
        return (str(start_at), str(end_at))
    interval_end = pendulum.instance(context['data_interval_end']).in_timezone(LOCAL_TZ)
    source_day = interval_end.subtract(days=1)
    return (source_day.start_of('day').format('YYYY-MM-DD HH:mm:ss'), source_day.end_of('day').format('YYYY-MM-DD HH:mm:ss'))

def load_wrt_sales(**context: object) -> None:
    start_at, end_at = _window_from_context(**context)
    source_connection = MsSqlHook(mssql_conn_id=WRT_SQLSERVER_CONNECTION).get_conn()
    target_connection = MsSqlHook(mssql_conn_id=SQLSERVER_CONNECTION).get_conn()
    try:
        row_count = sync_wrt_sales(source_connection, target_connection, start_at=start_at, end_at=end_at)
    finally:
        source_connection.close()
        target_connection.close()
    print(f'WRT -> SQL Server sync completed: {row_count} rows, {start_at} to {end_at}.')
with DAG(dag_id='wrt_sqlserver_to_sqlserver_daily', description='Read WRT warranty sales from SQL Server and append into dbo.WRT_SO (SQL Server).', start_date=pendulum.datetime(2026, 9, 14, tz=LOCAL_TZ), schedule='30 1 * * *', catchup=False, tags=['wrt', 'sqlserver', 'sales-orders'], default_args={'retries': 2, 'retry_delay': pendulum.duration(minutes=5)}) as dag:
    PythonOperator(task_id='load_wrt_sales', python_callable=load_wrt_sales)
