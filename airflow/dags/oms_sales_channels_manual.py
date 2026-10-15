"""Danh muc kenh ban OMS -> dbo.OMS_SALES_CHANNELS. KHONG co lich: chay khi bam "Cap nhat kenh ban" o Bao cao > E-commerce
(web goi Airflow REST API) hoac bam Trigger tren Airflow UI."""

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
from services.pipeline.oms_sales_channels import sync_oms_sales_channels

LOCAL_TZ = 'Asia/Ho_Chi_Minh'
SQLSERVER_CONNECTION = 'sqlserver_tracking'


def load_oms_sales_channels(**_context: object) -> None:
    target_connection = MsSqlHook(mssql_conn_id=SQLSERVER_CONNECTION).get_conn()
    try:
        row_count = sync_oms_sales_channels(target_connection)
    finally:
        target_connection.close()
    print(f'OMS sales channels -> SQL Server: {row_count} kenh.')


with DAG(
    dag_id='oms_sales_channels_manual',
    description='Manual only: OMS sales channels (online + offline) into dbo.OMS_SALES_CHANNELS.',
    start_date=pendulum.datetime(2026, 10, 15, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    # khong co lich nen bat san (moi truong dat DAGS_ARE_PAUSED_AT_CREATION=true) de nut tren web chay duoc ngay
    is_paused_upon_creation=False,
    tags=['oms', 'sqlserver', 'manual'],
    # khong retry: refresh token OMS bi thay moi lan dang nhap, lan loi nen xem log truoc khi chay lai
    default_args={'retries': 0},
) as dag:
    PythonOperator(task_id='load_oms_sales_channels', python_callable=load_oms_sales_channels)
