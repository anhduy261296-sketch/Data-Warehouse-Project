/*
 * Bang DataTables server-side dung chung (gop reconciliation.js + detail.js cu).
 *
 * 2 kieu bang:
 *   "recon"  - Data Tracking (doi soat): loc Status Sync + loc ngay (+ SO Status voi WRT), nut Excel.
 *   "detail" - Chi tiet don hang / Bao cao NV: nut chon cot + nut Excel, loc ngay neu options.dateFilter.
 *
 * Trang chi can khai bao cot trong pages/<menu>/*.js va goi DataTablePage.autoInit(registry):
 *   <table data-table-key="ecom" id="...">  ->  registry["ecom"] = { kind, endpoints, columns, ... }
 */

// Menu chon cot nam trong .table-responsive (overflow) -> cho tran ra ngoai khi dang mo
$(document).on("show.bs.dropdown", ".dt-buttons", function () {
  $(this).closest(".table-responsive").css("overflow", "visible");
});
$(document).on("hide.bs.dropdown", ".dt-buttons", function () {
  $(this).closest(".table-responsive").css("overflow", "auto");
});

const EXPORT_EXCEL_ICON = `
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V8l-3-6Z" fill="#F1F8F4" stroke="#1D6F42" stroke-width="1.4"/>
    <path d="M14 2v4a2 2 0 0 0 2 2h3" stroke="#1D6F42" stroke-width="1.4" stroke-linejoin="round"/>
    <path d="M9.5 13.5v5.5m0 0l-2.2-2.2m2.2 2.2l2.2-2.2" stroke="#1D6F42" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>
`;
const EXPORT_BUTTON_CLASS =
  "btn btn-sm bg-white border shadow-sm d-inline-flex align-items-center justify-content-center detail-export-btn";

// Thanh cong cu: [o loc ...] [o tim kiem] [nut]   /   bang   /   [thong tin] [so dong + phan trang]
const DT_DOM_FOOTER =
  "<'row'<'col-sm-12't>>" + "<'row align-items-center'<'col-sm-6'i>" + "<'col-sm-6 d-flex justify-content-end align-items-center'lp>>";
const dtToolbarDom = (slots) =>
  "<'row align-items-center'<'col-sm-12 d-flex justify-content-end align-items-center'" + slots + "fB>>" + DT_DOM_FOOTER;

/* ---------- Cot dung chung ---------- */
const COLUMNS = Object.freeze({
  /** Status Sync cua bang doi soat. */
  statusSync: {
    data: "status_sync",
    title: "Status Sync",
    orderable: false,
    render: (data) => renderStatusSyncBadge(data),
  },
  /** Status Sync cua bang chi tiet: chua co -> "Chua doi soat". */
  statusSyncDetail: {
    data: "status_sync",
    title: "Status Sync",
    orderable: false,
    render: (data) => (data ? renderStatusSyncBadge(data) : `<span class="badge badge-secondary">${APP.MESSAGES.NOT_RECONCILED}</span>`),
  },
  amount: (field, title, visible = true) => ({ data: field, title, className: "text-right", visible, render: (d) => formatAmount(d) }),
  datetime: (field, title, visible = true) => ({ data: field, title, visible, render: (d) => formatDateTime(d) }),
  refreshedAt: { data: "refreshed_at", title: "Cập nhật lúc", render: (d) => formatDateTime(d) },
});

const DataTablePage = (function () {
  const tables = {};

  function dateInputValue(daysAgo) {
    const d = new Date();
    d.setDate(d.getDate() - daysAgo);
    return d.toISOString().slice(0, 10);
  }

  /** O "Tu ngay - Den ngay" (mac dinh 30 ngay gan nhat, toi da APP.DATE_FILTER_MAX_RANGE_DAYS ngay). */
  function addDateRangeFilter(tableId) {
    const maxDays = APP.DATE_FILTER_MAX_RANGE_DAYS;
    $(`#${tableId}_wrapper .detail-date-filter`).html(`
      <div class="d-flex align-items-center">
        <label class="mb-0 mr-1 small text-muted">Từ ngày</label>
        <input type="date" class="form-control form-control-sm mr-2 detail-date-input" id="${tableId}_date_from">
        <label class="mb-0 mr-1 small text-muted">Đến ngày</label>
        <input type="date" class="form-control form-control-sm mr-2 detail-date-input" id="${tableId}_date_to">
        <button type="button" class="btn btn-sm btn-primary" id="${tableId}_date_search">Tìm</button>
      </div>
    `);
    const $from = $(`#${tableId}_date_from`);
    const $to = $(`#${tableId}_date_to`);
    $from.val(dateInputValue(maxDays));
    $to.val(dateInputValue(0));

    // giu khoang ngay <= maxDays: doi o nao thi keo o con lai theo
    function clampRange(changedField) {
      const fromDate = new Date($from.val());
      const toDate = new Date($to.val());
      if (isNaN(fromDate) || isNaN(toDate)) return;
      const diffDays = Math.round((toDate - fromDate) / 86400000);
      if (diffDays > maxDays) {
        if (changedField === "from") {
          const cappedTo = new Date(fromDate);
          cappedTo.setDate(cappedTo.getDate() + maxDays);
          $to.val(cappedTo.toISOString().slice(0, 10));
        } else {
          const cappedFrom = new Date(toDate);
          cappedFrom.setDate(cappedFrom.getDate() - maxDays);
          $from.val(cappedFrom.toISOString().slice(0, 10));
        }
      } else if (diffDays < 0) {
        $to.val($from.val());
      }
    }

    $from.on("change", () => {
      clampRange("from");
      tables[tableId].draw();
    });
    $to.on("change", () => {
      clampRange("to");
      tables[tableId].draw();
    });
    $(`#${tableId}_date_search`).on("click", () => {
      clampRange("to");
      tables[tableId].draw();
    });
  }

  function addStatusSyncFilter(tableId) {
    const $select = $(
      '<select class="form-control form-control-sm">' +
        '<option value="">Tất cả</option>' +
        `<option value="${APP.STATUS_SYNC.SYNC}">${APP.STATUS_SYNC.SYNC}</option>` +
        `<option value="${APP.STATUS_SYNC.NOT_SYNC}">${APP.STATUS_SYNC.NOT_SYNC}</option>` +
        "</select>",
    );
    $select.on("change", () => tables[tableId].draw());
    $(`#${tableId}_wrapper`).find(".recon-status-filter").append($select);
  }

  function addSoStatusFilter(tableId, optionsEndpoint) {
    const $select = $('<select class="form-control form-control-sm"><option value="">Tất cả</option></select>');
    $select.on("change", () => tables[tableId].draw());
    $(`#${tableId}_wrapper`).find(".recon-so-status-filter").append($select);
    Api.get(optionsEndpoint).done((payload) => {
      (payload.options || []).forEach((value) => $select.append($("<option>").attr("value", value).text(value)));
    });
  }

  /** Nut xuat Excel: gui kem khoang ngay (+ tu khoa tim kiem neu includeSearch). */
  function exportButton(tableId, exportEndpoint, includeSearch) {
    return {
      text: EXPORT_EXCEL_ICON,
      titleAttr: APP.MESSAGES.EXPORT_EXCEL,
      className: EXPORT_BUTTON_CLASS,
      action: function () {
        const searchValue = includeSearch && tables[tableId] ? tables[tableId].search() : "";
        Api.download(exportEndpoint, {
          "search[value]": searchValue,
          date_from: $(`#${tableId}_date_from`).val(),
          date_to: $(`#${tableId}_date_to`).val(),
        });
      },
    };
  }

  /** Nut chon cot (cot visible:false mac dinh an) + muc "Chon tat ca / Huy chon tat ca". */
  function columnPickerButton(columns) {
    return {
      extend: "colvis",
      text: '<i class="fas fa-cog"></i>',
      titleAttr: APP.MESSAGES.CHOOSE_COLUMNS,
      className: "btn btn-sm btn-outline-secondary detail-colvis-btn",
      align: "button-right",
      prefixButtons: [
        {
          text: APP.MESSAGES.SELECT_ALL,
          action: function (e, dt, node) {
            if (dt.columns(":hidden").count() > 0) {
              dt.columns(":hidden").visible(true);
              $(node).text(APP.MESSAGES.UNSELECT_ALL);
            } else {
              columns.forEach((col, idx) => {
                if (col.visible === false) dt.column(idx).visible(false);
              });
              $(node).text(APP.MESSAGES.SELECT_ALL);
            }
          },
        },
      ],
    };
  }

  /**
   * Tao bang. options: { kind: "recon" | "detail", exportEndpoint, dateFilter (detail) }.
   * Tra ve Promise xong khi bang ve lan dau.
   */
  function render(tableId, endpoint, columns, options) {
    const isRecon = options.kind === "recon";
    const withDateFilter = isRecon || !!options.dateFilter;
    return new Promise((resolve) => {
      tables[tableId] = $(`#${tableId}`).DataTable({
        serverSide: true,
        processing: true,
        ajax: {
          url: `${ENDPOINTS.API_BASE}${endpoint}`,
          data: function (d) {
            if (isRecon) {
              d.status_sync = $(`#${tableId}_wrapper .recon-status-filter select`).val() || "";
              d.so_status = $(`#${tableId}_wrapper .recon-so-status-filter select`).val() || "";
            }
            if (withDateFilter) {
              d.date_from = $(`#${tableId}_date_from`).val() || "";
              d.date_to = $(`#${tableId}_date_to`).val() || "";
            }
          },
        },
        columns,
        order: [],
        dom: isRecon
          ? dtToolbarDom("<'detail-date-filter mr-2'><'recon-so-status-filter mr-2'><'recon-status-filter mr-2'>")
          : dtToolbarDom("<'detail-date-filter mr-2'>"),
        buttons: [
          ...(isRecon ? [] : [columnPickerButton(columns)]),
          ...(options.exportEndpoint ? [exportButton(tableId, options.exportEndpoint, !isRecon)] : []),
        ],
        language: { lengthMenu: "_MENU_" },
        initComplete: function () {
          if (withDateFilter) {
            addDateRangeFilter(tableId);
            tables[tableId].draw();
          }
          resolve();
        },
      });
      if (isRecon) addStatusSyncFilter(tableId);
    });
  }

  function load(tableId, endpoint, columns, options) {
    return Loading.wrapPage(() => render(tableId, endpoint, columns, options || {}), APP.MESSAGES.LOADING);
  }

  /**
   * Khoi tao bang cua trang theo the <table data-table-key="...">.
   * registry[key] = { kind, endpoints: { report, export, soStatusOptions? }, columns, dateFilter?, soStatusFilter? }
   */
  function autoInit(registry) {
    $(function () {
      $("table[data-table-key]").each(function () {
        const cfg = registry[$(this).data("tableKey")];
        if (!cfg) return;
        const tableId = this.id;
        load(tableId, cfg.endpoints.report, cfg.columns, {
          kind: cfg.kind,
          exportEndpoint: cfg.endpoints.export,
          dateFilter: cfg.dateFilter,
        }).then(() => {
          if (cfg.soStatusFilter) addSoStatusFilter(tableId, cfg.endpoints.soStatusOptions);
        });
      });
    });
  }

  return { load, autoInit, addSoStatusFilter, exportButton, get: (tableId) => tables[tableId] };
})();
