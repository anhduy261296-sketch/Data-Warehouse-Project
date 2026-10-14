/*
 * Hang so dung chung phia trinh duyet. Muon doi mau, thong bao, gioi han... chi sua o day.
 * (Duong dan API nam o core/endpoints.js)
 */
const APP = Object.freeze({
  LOCALE: "vi-VN",
  TIMEZONE: "Asia/Ho_Chi_Minh",
  FONT_FAMILY: '"Be Vietnam Pro", "Segoe UI", sans-serif',

  MESSAGES: Object.freeze({
    LOADING: "Đang tải dữ liệu...",
    LOADING_SHORT: "Đang tải...",
    NO_DATA: "Không có dữ liệu",
    LOAD_FAILED_RETRY: "Không tải được dữ liệu. Bấm Làm mới để thử lại.",
    EXPORT_EXCEL: "Xuất Excel",
    CHOOSE_COLUMNS: "Chọn cột hiển thị",
    SELECT_ALL: "Chọn tất cả",
    UNSELECT_ALL: "Hủy chọn tất cả",
    NOT_RECONCILED: "Chưa đối soát",
  }),

  // Bo loc ngay cua bang don hang: so ngay toi da giua Tu ngay - Den ngay (backend cung chan MAX_DATE_RANGE_DAYS)
  DATE_FILTER_MAX_RANGE_DAYS: 30,

  STATUS_SYNC: Object.freeze({ SYNC: "Sync", NOT_SYNC: "Not Sync" }),

  // Doi chieu ton kho SAP - WMS: trang thai -> class badge
  INVENTORY_STATUS_BADGE: Object.freeze({
    Khớp: "badge-success",
    Lệch: "badge-danger",
    "Chỉ có SAP": "badge-warning",
    "Chỉ có WMS": "badge-info",
    "Không quản lý trên WMS": "badge-secondary",
  }),

  COLORS: Object.freeze({
    PRIMARY: "#820606",
    CHART_TEXT: "#5a5f6b",
    CHART_GRID: "#eef0f3",
    NEUTRAL: "#94a3b8",
    NEUTRAL_LIGHT: "#cbd5e1",
    SAP: Object.freeze({ text: "#1e7e34", fill: "rgba(40, 167, 69, 0.45)", border: "#28a745" }),
    WMS: Object.freeze({ text: "#1565c0", fill: "rgba(21, 101, 192, 0.40)", border: "#1565c0" }),
    MATCH: "#d3adf7",
    DIFF: "#e57373",
    // mau theo thu tu kho / nhom hang tren bieu do
    PALETTE: Object.freeze([
      "#3b82f6",
      "#22c3a6",
      "#f59e0b",
      "#a855f7",
      "#ec4899",
      "#60a5fa",
      "#94a3b8",
      "#ef4444",
      "#14b8a6",
      "#f97316",
      "#84cc16",
      "#6366f1",
      "#06b6d4",
      "#d946ef",
      "#eab308",
      "#10b981",
      "#8b5cf6",
      "#fb7185",
    ]),
  }),

  // Cache trang da xem cua bang DataTables (trong bo nho trang)
  PAGE_CACHE_MAX: 200,

  DATATABLE: Object.freeze({
    PAGE_LENGTH: 10,
    // ngon ngu cho bang bao cao moi (bang cu giu mac dinh tieng Anh cua DataTables + lengthMenu "_MENU_")
    LANGUAGE_VI: Object.freeze({
      thousands: ".",
      lengthMenu: "_MENU_ / trang",
      infoEmpty: "Không có dữ liệu",
      infoFiltered: "(lọc từ _MAX_ dòng)",
      zeroRecords: "Không có dữ liệu",
      emptyTable: "Không có dữ liệu",
      processing: "Đang tải...",
      paginate: { previous: "‹", next: "›" },
    }),
  }),
});
