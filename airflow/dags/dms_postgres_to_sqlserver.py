from __future__ import annotations
import sys
from pathlib import Path
import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
from airflow.providers.postgres.hooks.postgres import PostgresHook
PROJECT_ROOT = Path('/opt/airflow/project')
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from services.pipeline.dms_sales_orders import sync_dms_sales_orders
LOCAL_TZ = 'Asia/Ho_Chi_Minh'
DMS_POSTGRES_CONNECTION = 'dms_postgres'
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

def load_dms_sales_orders(**context: object) -> None:
    start_at, end_at = _window_from_context(**context)
    source_connection = PostgresHook(postgres_conn_id=DMS_POSTGRES_CONNECTION).get_conn()
    target_connection = MsSqlHook(mssql_conn_id=SQLSERVER_CONNECTION).get_conn()
    try:
        row_count = sync_dms_sales_orders(source_connection, target_connection, start_at=start_at, end_at=end_at)
    finally:
        source_connection.close()
        target_connection.close()
    print(f'DMS -> SQL Server sync completed: {row_count} rows, {start_at} to {end_at}.')
with DAG(dag_id='dms_postgres_to_sqlserver_daily', description='Read DMS sales orders from PostgreSQL and append into dbo.DMS_SO (SQL Server).', start_date=pendulum.datetime(2026, 9, 13, tz=LOCAL_TZ), schedule='0 0 * * *', catchup=False, tags=['dms', 'postgres', 'sqlserver', 'sales-orders'], default_args={'retries': 2, 'retry_delay': pendulum.duration(minutes=5)}) as dag:
    PythonOperator(task_id='load_dms_sales_orders', python_callable=load_dms_sales_orders)
