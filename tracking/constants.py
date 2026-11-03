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
# Lỗi tạm thời tự thử lại: số giây chờ trước mỗi lần thử tiếp (2 phần tử = tối đa 3 lần gọi).
ZNS_RETRY_DELAYS = tuple(float(x) for x in os.getenv('ZNS_RETRY_DELAYS', '2,5').split(',') if x.strip())
ZNS_PAUSE_AFTER = int(os.getenv('ZNS_PAUSE_AFTER', '5'))
ZNS_MAX_MANUAL_RETRIES = int(os.getenv('ZNS_MAX_MANUAL_RETRIES', '3'))
# Lô "Đang gửi" im quá số giây này thì tiến trình gửi đã dừng: phải lớn hơn thời gian gửi một khách lâu nhất (timeout x số lần gọi + giãn cách).
ZNS_RESUME_AFTER_SECONDS = int(os.getenv('ZNS_RESUME_AFTER_SECONDS', '180'))
ZNS_WATCH_INTERVAL_SECONDS = int(os.getenv('ZNS_WATCH_INTERVAL_SECONDS', '60'))
# Dừng lâu hơn số giây này thì không tự gửi tiếp (tin có thể đã hết hạn): lô chuyển "Tạm dừng" để người dùng quyết định.
ZNS_RESUME_MAX_SECONDS = int(os.getenv('ZNS_RESUME_MAX_SECONDS', '7200'))
# Tự chạy tiếp tối đa chừng này lần mỗi lô: quá thì tạm dừng, tránh lặp vô hạn mà mỗi vòng vẫn gửi thêm tin.
ZNS_MAX_AUTO_RESUMES = int(os.getenv('ZNS_MAX_AUTO_RESUMES', '3'))
# Chừng này khách liên tiếp đều lỗi (bất kỳ loại lỗi nào, không khách nào thành công xen giữa) thì tạm dừng lô.
ZNS_PAUSE_AFTER_ERRORS = int(os.getenv('ZNS_PAUSE_AFTER_ERRORS', '20'))

REPORT_CACHE_TTL = 24 * 3600
REPORT_CACHE_MAX_ITEM_BYTES = int(os.getenv('REPORT_CACHE_MAX_ITEM_KB', os.getenv('STOCK_REPORT_CACHE_MAX_ITEM_KB', '64'))) * 1024
REPORT_VERSION_TTL = 60
