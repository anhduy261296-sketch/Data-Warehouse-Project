/*
 * Duong dan API, nhom theo menu (Data Tracking / Chi tiet don hang / Bao cao).
 * Them trang moi: them 1 muc o day, khong viet cung URL trong code trang.
 */
const ENDPOINTS = Object.freeze({
  API_BASE: "",

  // Menu "Data Tracking"
  dataTracking: Object.freeze({
    ecom: Object.freeze({ report: "/api/recon/ecom/report/", export: "/api/recon/ecom/export/" }),
    dmsDuyet: Object.freeze({ report: "/api/recon/dms-duyet/report/", export: "/api/recon/dms-duyet/export/" }),
    dmsXuatKho: Object.freeze({ report: "/api/recon/dms-xuatkho/report/", export: "/api/recon/dms-xuatkho/export/" }),
    wrt: Object.freeze({
      report: "/api/recon/wrt/report/",
      export: "/api/recon/wrt/export/",
      soStatusOptions: "/api/recon/wrt/so-status-options/",
    }),
    inventory: Object.freeze({
      report: "/api/recon/inventory/report/",
      export: "/api/recon/inventory/export/",
      meta: "/api/recon/inventory/meta/",
      detail: "/api/recon/inventory/detail/",
      detailExport: "/api/recon/inventory/detail/export/",
      diffList: "/api/recon/inventory/diff-list/",
      diffExport: "/api/recon/inventory/diff-list/export/",
    }),
  }),

  // Menu "Chi tiet don hang"
  orderDetail: Object.freeze({
    ecom: Object.freeze({ report: "/api/detail/ecom/report/", export: "/api/detail/ecom/export/" }),
    dmsDuyet: Object.freeze({ report: "/api/detail/dms-duyet/report/", export: "/api/detail/dms-duyet/export/" }),
    dmsXuatKho: Object.freeze({ report: "/api/detail/dms-xuatkho/report/", export: "/api/detail/dms-xuatkho/export/" }),
    wrt: Object.freeze({ report: "/api/detail/wrt/report/", export: "/api/detail/wrt/export/" }),
  }),

  // Menu "Bao cao"
  reports: Object.freeze({
    employeeDms: Object.freeze({ report: "/api/detail/employee/dms/report/", export: "/api/detail/employee/dms/export/" }),
    employeeOms: Object.freeze({ report: "/api/detail/employee/oms/report/", export: "/api/detail/employee/oms/export/" }),
    inventory: Object.freeze({
      meta: "/api/report/inventory/meta/",
      kpi: "/api/report/inventory/kpi/",
      bySku: "/api/report/inventory/by-sku/",
      topSku: "/api/report/inventory/top-sku/",
      byWarehouse: "/api/report/inventory/by-warehouse/",
      byGroup: "/api/report/inventory/by-group/",
      byLocation: "/api/report/inventory/by-location/",
      byLocationExport: "/api/report/inventory/by-location/export/",
      export: "/api/report/inventory/export/",
    }),
    ecom: Object.freeze({
      meta: "/api/report/ecom/meta/",
      kpi: "/api/report/ecom/kpi/",
      daily: "/api/report/ecom/daily/",
      bySale: "/api/report/ecom/by-sale/",
      topProducts: "/api/report/ecom/top-products/",
      orders: "/api/report/ecom/orders/",
      ordersExport: "/api/report/ecom/orders/export/",
      channelsRefresh: "/api/report/ecom/channels/refresh/",
      channelsRefreshStatus: "/api/report/ecom/channels/refresh/status/",
    }),
  }),
});
