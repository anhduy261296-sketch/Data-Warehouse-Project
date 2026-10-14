"""Thanh phan dung chung cho cac pipeline (Airflow nap truc tiep, khong qua Django).

constants.py  - schema, danh sach kho PGI, kho dac biet
db.py         - kiem tra bang ton tai, bat fast_executemany
wms_client.py - dang nhap WMS Smartlog + goi API co retry (401 / server busy / loi mang)
"""
