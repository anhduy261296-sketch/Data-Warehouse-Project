"""Hang so dung chung giua cac pipeline. Them / bot kho chi sua o day.

Luu y: phia web (Django) co ban sao cac hang so kho trong tracking/constants.py (Airflow khong nap Django) -
doi o day thi doi ca ben do.
"""

from __future__ import annotations

TARGET_SCHEMA = 'dbo'

# Kho PGI tren WMS Smartlog (ma WHxxx) - pipeline WMS keo lan luot tung kho
PGI_WAREHOUSE_CODES = [
    'WH102',
    'WH103',
    'WH104',
    'WH105',
    'WH106',
    'WH107',
    'WH108',
    'WH109',
    'WH110',
    'WH111',
    'WH112',
    'WH113',
    'WH114',
    'WH116',
    'WH117',
    'WH118',
    'WH119',
    'WH998',
]

# Ma kho SAP (Wxxx) khong quan ly tren WMS -> doi chieu ton danh dau "Khong quan ly tren WMS"
NON_WMS_WAREHOUSES = ('W101', 'W999')
# Kho khong quan ly trang thai hang -> doi chieu SAP-WMS chi theo ma hang + kho
STATUS_FREE_WAREHOUSES = ('W114', 'W998')

# SQL Server gioi han 2100 tham so / cau lenh -> chia lo insert duoi muc nay
MAX_SQL_PARAMS = 2090
