from __future__ import annotations
import sys
from pathlib import Path
import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup
PROJECT_ROOT = Path('/opt/airflow/project')
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from services.pipeline.tasks import backup_tracking, build_tracking, extract_to_draft, upsert_sale_orders

def logical_date(**context: object) -> str:
    return context['ds']

def call_extract(system: str, **context: object) -> None:
    extract_to_draft(system, logical_date(**context))

def call_tracking(source: str, **context: object) -> None:
    build_tracking(source, logical_date(**context))

def call_backup(**context: object) -> None:
    backup_tracking(logical_date(**context))

def call_final(**context: object) -> None:
    upsert_sale_orders(logical_date(**context))
with DAG(dag_id='systems_tracking_daily', description='DMS/OMS/SAP/WRT/WMS -> draft -> tracking -> backup -> PGI_SaleOrders', start_date=pendulum.datetime(2026, 9, 13, tz='Asia/Ho_Chi_Minh'), schedule='0 22 * * *', catchup=False, tags=['systems-tracking', 'daily'], default_args={'retries': 1}) as dag:
    with TaskGroup(group_id='extract_to_draft') as extract:
        extract_tasks = [PythonOperator(task_id=f'extract_{system.lower()}', python_callable=call_extract, op_kwargs={'system': system}) for system in ('DMS', 'OMS', 'SAP', 'WRT', 'WMS')]
    with TaskGroup(group_id='build_tracking') as tracking:
        tracking_tasks = [PythonOperator(task_id=f'track_{source.lower()}', python_callable=call_tracking, op_kwargs={'source': source}) for source in ('DMS', 'OMS', 'WRT')]
    backup = PythonOperator(task_id='backup_tracking', python_callable=call_backup)
    final = PythonOperator(task_id='upsert_pgi_sale_orders', python_callable=call_final)
    for extract_task in extract_tasks:
        for tracking_task in tracking_tasks:
            extract_task >> tracking_task
    for tracking_task in tracking_tasks:
        tracking_task >> backup
    backup >> final
