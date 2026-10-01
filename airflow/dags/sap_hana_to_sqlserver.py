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
from services.pipeline.sap_sales_delivery import sync_sap_sales_delivery
LOCAL_TZ = 'Asia/Ho_Chi_Minh'
SAP_HANA_CONNECTION = 'sap_hana'
SQLSERVER_CONNECTION = 'sqlserver_tracking'

def _get_sap_hana_conn():
    from hdbcli import dbapi
    conn = BaseHook.get_connection(SAP_HANA_CONNECTION)
    return dbapi.connect(address=conn.host, port=conn.port, user=conn.login, password=conn.password)

def _process_date_from_context(**context: object) -> str:
    dag_run = context.get('dag_run')
    run_conf = getattr(dag_run, 'conf', None) or {}
    process_date = run_conf.get('process_date')
    if process_date:
        return str(process_date)
    interval_end = pendulum.instance(context['data_interval_end']).in_timezone(LOCAL_TZ)
    source_day = interval_end.subtract(days=1)
    return source_day.format('YYYY-MM-DD')

def load_sap_sales_delivery(**context: object) -> None:
    process_date = _process_date_from_context(**context)
    source_connection = _get_sap_hana_conn()
    target_connection = MsSqlHook(mssql_conn_id=SQLSERVER_CONNECTION).get_conn()
    try:
        row_count = sync_sap_sales_delivery(source_connection, target_connection, process_date=process_date)
    finally:
        source_connection.close()
        target_connection.close()
    print(f'SAP -> SQL Server sync completed: {row_count} rows for {process_date}.')
with DAG(dag_id='sap_hana_to_sqlserver_daily', description='Read SAP sales delivery from SAP HANA and upsert into dbo.SAP_SO_All (SQL Server).', start_date=pendulum.datetime(2026, 9, 14, tz=LOCAL_TZ), schedule='30 0 * * *', catchup=False, max_active_runs=1, tags=['sap', 'hana', 'sqlserver', 'sales-orders'], default_args={'retries': 2, 'retry_delay': pendulum.duration(minutes=5)}) as dag:
    PythonOperator(task_id='load_sap_sales_delivery', python_callable=load_sap_sales_delivery)
