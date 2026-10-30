from django.urls import path
from django.views.generic import RedirectView

from .queries.orders import DETAIL_CONFIGS, EMPLOYEE_REPORT_CONFIG_DMS, EMPLOYEE_REPORT_CONFIG_OMS, RECON_CONFIGS
from .queries.ecom import ECOM_DETAIL_CONFIG
from .queries.recon_inventory import INVENTORY_CONFIG
from .views import data_tracking, messaging, reports
from .menu import HOME_URL_NAME
from .views.common import datatable_export_view, datatable_report_view, page_view


def datatable_routes(page_url: str, api_url: str, name: str, template: str, config, export_filename: str):
    return [
        path(page_url, page_view(template), name=name),
        path(f'{api_url}report/', datatable_report_view(config, f'{name}-report'), name=f'{name}-report'),
        path(f'{api_url}export/', datatable_export_view(config, export_filename), name=f'{name}-export'),
    ]


ORDER_PAGES = (
    ('ecom', 'ecom', 'ecom'),
    ('dms-duyet', 'dms-duyet', 'dms_duyet'),
    ('dms-xuatkho', 'dms-xuatkho', 'dms_xuatkho'),
    ('wrt', 'wrt', 'wrt'),
)

urlpatterns = [
    path('', RedirectView.as_view(pattern_name=HOME_URL_NAME), name='home'),
]

for slug, key, tpl in ORDER_PAGES:
    urlpatterns += datatable_routes(
        f'recon/{slug}/',
        f'api/recon/{slug}/',
        f'recon-{slug}',
        f'data_tracking/{tpl}.html',
        RECON_CONFIGS[key],
        f'data_tracking_{tpl}.xlsx',
    )
urlpatterns += [path('api/recon/wrt/so-status-options/', data_tracking.recon_wrt_so_status_options, name='recon-wrt-so-status-options')]
urlpatterns += datatable_routes(
    'recon/inventory/',
    'api/recon/inventory/',
    'recon-inventory',
    'data_tracking/inventory.html',
    INVENTORY_CONFIG,
    'data_tracking_inventory.xlsx',
)
urlpatterns += [
    path('api/recon/inventory/meta/', data_tracking.recon_inventory_meta, name='recon-inventory-meta'),
    path('api/recon/inventory/detail/', data_tracking.recon_inventory_detail, name='recon-inventory-detail'),
    path('api/recon/inventory/detail/export/', data_tracking.recon_inventory_detail_export, name='recon-inventory-detail-export'),
    path('api/recon/inventory/diff-list/', data_tracking.recon_inventory_diff_list, name='recon-inventory-diff-list'),
    path('api/recon/inventory/diff-list/export/', data_tracking.recon_inventory_diff_export, name='recon-inventory-diff-export'),
]

for slug, key, tpl in ORDER_PAGES:
    urlpatterns += datatable_routes(
        f'detail/{slug}/', f'api/detail/{slug}/', f'detail-{slug}', f'order_detail/{tpl}.html', DETAIL_CONFIGS[key], f'chi_tiet_{tpl}.xlsx'
    )

urlpatterns += datatable_routes(
    'detail/employee/dms/',
    'api/detail/employee/dms/',
    'detail-employee-dms',
    'reports/employee_dms.html',
    EMPLOYEE_REPORT_CONFIG_DMS,
    'chi_tiet_don_hang_theo_nhan_vien_dms.xlsx',
)
urlpatterns += datatable_routes(
    'detail/employee/oms/',
    'api/detail/employee/oms/',
    'detail-employee-oms',
    'reports/employee_oms.html',
    EMPLOYEE_REPORT_CONFIG_OMS,
    'chi_tiet_don_hang_theo_nhan_vien_oms.xlsx',
)
urlpatterns += [
    path('report/inventory/', page_view('reports/inventory.html'), name='report-inventory'),
    path('api/report/inventory/meta/', reports.inventory_meta, name='report-inventory-meta'),
    path('api/report/inventory/kpi/', reports.inventory_kpi, name='report-inventory-kpi'),
    path('api/report/inventory/by-sku/', reports.inventory_by_sku, name='report-inventory-by-sku'),
    path('api/report/inventory/top-sku/', reports.inventory_top_sku, name='report-inventory-top-sku'),
    path('api/report/inventory/by-warehouse/', reports.inventory_by_warehouse, name='report-inventory-by-warehouse'),
    path('api/report/inventory/by-location/', reports.inventory_by_location, name='report-inventory-by-location'),
    path('api/report/inventory/by-location/export/', reports.inventory_by_location_export, name='report-inventory-by-location-export'),
    path('api/report/inventory/by-group/', reports.inventory_by_group, name='report-inventory-by-group'),
    path('api/report/inventory/export/', reports.inventory_export, name='report-inventory-export'),
]
urlpatterns += [
    path('report/ecom/', page_view('reports/ecom.html'), name='report-ecom'),
    path('api/report/ecom/meta/', reports.ecom_meta, name='report-ecom-meta'),
    path('api/report/ecom/kpi/', reports.ecom_kpi, name='report-ecom-kpi'),
    path('api/report/ecom/daily/', reports.ecom_daily, name='report-ecom-daily'),
    path('api/report/ecom/by-sale/', reports.ecom_by_sale, name='report-ecom-by-sale'),
    path('api/report/ecom/top-products/', reports.ecom_top_products, name='report-ecom-top-products'),
    path('api/report/ecom/orders/', datatable_report_view(ECOM_DETAIL_CONFIG, 'report-ecom-orders'), name='report-ecom-orders'),
    path(
        'api/report/ecom/orders/export/',
        datatable_export_view(ECOM_DETAIL_CONFIG, 'chi_tiet_don_hang_ecom.xlsx'),
        name='report-ecom-orders-export',
    ),
    path('api/report/ecom/channels/refresh/', reports.ecom_channels_refresh, name='report-ecom-channels-refresh'),
    path('api/report/ecom/channels/refresh/status/', reports.ecom_channels_refresh_status, name='report-ecom-channels-refresh-status'),
]
urlpatterns += [
    path('zns/templates/', page_view('messaging/templates.html'), name='zns-templates'),
    path('zns/templates/new/', messaging.template_editor, name='zns-template-new'),
    path('zns/templates/<int:template_id>/', messaging.template_editor, name='zns-template-edit'),
    path('zns/send/', page_view('messaging/send.html'), name='zns-send'),
    path('api/zns/templates/', messaging.template_list, name='zns-template-list'),
    path('api/zns/templates/save/', messaging.template_save, name='zns-template-save'),
    path('api/zns/templates/export/', messaging.template_export, name='zns-template-export'),
    path('api/zns/templates/import/', messaging.template_import, name='zns-template-import'),
    path('api/zns/templates/sample/', messaging.template_sample, name='zns-template-sample'),
    path('api/zns/templates/<int:template_id>/', messaging.template_detail, name='zns-template-detail'),
    path('api/zns/templates/<int:template_id>/active/', messaging.template_active, name='zns-template-active'),
    path('api/zns/send/sample/', messaging.send_sample, name='zns-send-sample'),
    path('api/zns/send/upload/', messaging.send_upload, name='zns-send-upload'),
    path('api/zns/send/evaluate/', messaging.send_evaluate, name='zns-send-evaluate'),
    path('api/zns/send/confirm/', messaging.send_confirm, name='zns-send-confirm'),
    path('api/zns/batches/', messaging.batch_list, name='zns-batch-list'),
    path('api/zns/batches/<int:batch_id>/', messaging.batch_detail, name='zns-batch-detail'),
    path('api/zns/batches/<int:batch_id>/cancel/', messaging.batch_cancel, name='zns-batch-cancel'),
    path('api/zns/batches/<int:batch_id>/export/', messaging.batch_export, name='zns-batch-export'),
]
