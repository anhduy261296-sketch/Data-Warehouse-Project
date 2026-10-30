from __future__ import annotations

import os
import re

MAX_PAGE_LENGTH = 200
MAX_DATE_RANGE_DAYS = 30
EXPORT_MAX_ROWS = 50000

STATUS_TRACKING_TABLE = 'STATUS_TRACKING'

STATUS_FREE_WAREHOUSES = ('W114', 'W998')
INVENTORY_HIDDEN_STATUS = 'Không quản lý trên WMS'
INVENTORY_STATUS_VALUES = ('Khớp', 'Lệch', 'Chỉ có SAP', 'Chỉ có WMS', INVENTORY_HIDDEN_STATUS)
INVENTORY_DIFF_STATUSES = ('Lệch', 'Chỉ có SAP', 'Chỉ có WMS')
INVENTORY_DETAIL_MAX_ROWS = 20000
SAP_DOC_TYPE_CACHE_SEC = 600
SAP_DOC_DIRECTION = {15: 'Bán ra', 16: 'Hàng hoàn', 20: 'Nhập mua', 21: 'Trả NCC', 59: 'Nhập khác', 60: 'Xuất khác'}
STATUS_CHANGE_LABEL = 'Chuyển trạng thái'
STATUS_CHANGE_MATCH_DAYS = 3

WMS_WAREHOUSE_RE = re.compile(r'^WH\d{3}$')
STOCK_TOP_LIMIT = 10

ECOM_TOP_LIMIT = 10
ECOM_MAX_RANGE_DAYS = MAX_DATE_RANGE_DAYS

AIRFLOW_API_URL = os.getenv('AIRFLOW_API_URL', 'http://airflow-webserver:8080/api/v1')
AIRFLOW_API_USER = os.getenv('AIRFLOW_API_USER') or os.getenv('AIRFLOW_ADMIN_USER', 'airflow')
AIRFLOW_API_PASSWORD = os.getenv('AIRFLOW_API_PASSWORD') or os.getenv('AIRFLOW_ADMIN_PASSWORD', 'airflow')
OMS_ORDERS_DAG_ID = 'oms_orders_to_sqlserver_daily'
OMS_SALES_CHANNELS_DAG_ID = 'oms_sales_channels_manual'

# Gửi ZNS qua Incom Omni. Mặc định dry_run: KHÔNG gọi API, chỉ ghi nhận "Chạy thử".
# Chỉ khi ZNS_SEND_MODE=live (đặt trong .env) mới gửi tin thật.
ZNS_SEND_MODE = 'live' if os.getenv('ZNS_SEND_MODE', 'dry_run').strip().lower() == 'live' else 'dry_run'
ZNS_API_URL = os.getenv('ZNS_API_URL', 'https://omni.incom.vn/api/OmniMessage/SendMessage')
ZNS_ROUTE_RULE = [r.strip() for r in os.getenv('ZNS_ROUTE_RULE', '1').split(',') if r.strip()]
ZNS_ACCOUNTS = {
    'PGI': (os.getenv('ZNS_PGI_USERNAME', ''), os.getenv('ZNS_PGI_PASSWORD', '')),
    'AWG': (os.getenv('ZNS_AWG_USERNAME', ''), os.getenv('ZNS_AWG_PASSWORD', '')),
}
ZNS_SEND_DELAY_MS = int(os.getenv('ZNS_SEND_DELAY_MS', '300'))
ZNS_API_TIMEOUT = int(os.getenv('ZNS_API_TIMEOUT', '20'))

REPORT_CACHE_TTL = 24 * 3600
REPORT_CACHE_MAX_ITEM_BYTES = int(os.getenv('REPORT_CACHE_MAX_ITEM_KB', os.getenv('STOCK_REPORT_CACHE_MAX_ITEM_KB', '64'))) * 1024
REPORT_VERSION_TTL = 60
