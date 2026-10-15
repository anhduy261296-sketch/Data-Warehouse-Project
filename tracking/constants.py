"""Hang so dung chung phia web (Django). Doi gioi han / danh sach kho / nhan trang thai chi sua o day.

(Hang so cua pipeline Airflow nam trong services/pipeline - Airflow khong nap Django.)
"""

from __future__ import annotations

import os
import re

# ---- Bang DataTables / xuat Excel ----------------------------------------------------------------
MAX_PAGE_LENGTH = 200  # so dong toi da moi trang API tra ve
MAX_DATE_RANGE_DAYS = 30  # bo loc ngay bang don hang: khoang toi da (frontend: APP.DATE_FILTER_MAX_RANGE_DAYS)
EXPORT_MAX_ROWS = 50000  # so dong toi da moi file Excel

# ---- Data Tracking (doi soat don hang) -----------------------------------------------------------
STATUS_TRACKING_TABLE = 'STATUS_TRACKING'

# ---- Data Tracking > Ton kho SAP-WMS -------------------------------------------------------------
# Kho khong quan ly trang thai hang -> so sanh SAP-WMS chi theo ma hang + kho
STATUS_FREE_WAREHOUSES = ('W114', 'W998')
INVENTORY_HIDDEN_STATUS = 'Không quản lý trên WMS'  # an mac dinh khoi bang doi chieu
INVENTORY_STATUS_VALUES = ('Khớp', 'Lệch', 'Chỉ có SAP', 'Chỉ có WMS', INVENTORY_HIDDEN_STATUS)
INVENTORY_DIFF_STATUSES = ('Lệch', 'Chỉ có SAP', 'Chỉ có WMS')
INVENTORY_DETAIL_MAX_ROWS = 20000  # so chung tu toi da moi ben trong popup chi tiet
SAP_DOC_TYPE_CACHE_SEC = 600  # cache ten loai chung tu SAP (SAP_INOUT)
# SAP DocType -> chieu nhap/xuat hien trong popup (67 = chuyen kho / chuyen trang thai, xu ly rieng)
SAP_DOC_DIRECTION = {15: 'Bán ra', 16: 'Hàng hoàn', 20: 'Nhập mua', 21: 'Trả NCC', 59: 'Nhập khác', 60: 'Xuất khác'}
STATUS_CHANGE_LABEL = 'Chuyển trạng thái'
STATUS_CHANGE_MATCH_DAYS = 3  # ghep IT doi trang thai SAP <-> WMS lech toi da N ngay

# ---- Bao cao > Ton kho ---------------------------------------------------------------------------
WMS_WAREHOUSE_RE = re.compile(r'^WH\d{3}$')
STOCK_TOP_LIMIT = 10

# ---- Cache bao cao theo phien ban du lieu (tracking/core/cache.py, CACHES['reports'] trong settings) -------
REPORT_CACHE_TTL = 24 * 3600
# ket qua lon hon muc nay thi khong cache (STOCK_REPORT_* la ten bien cu, van doc de tuong thich)
REPORT_CACHE_MAX_ITEM_BYTES = int(os.getenv('REPORT_CACHE_MAX_ITEM_KB', os.getenv('STOCK_REPORT_CACHE_MAX_ITEM_KB', '64'))) * 1024
REPORT_VERSION_TTL = 60  # doc lai phien ban du lieu toi da moi N giay
