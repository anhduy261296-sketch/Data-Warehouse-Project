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

const DT_DOM_FOOTER =
  "<'row'<'col-sm-12't>>" + "<'row align-items-center'<'col-sm-6'i>" + "<'col-sm-6 d-flex justify-content-end align-items-center'lp>>";
const dtToolbarDom = (slots) =>
  "<'row align-items-center'<'col-sm-12 d-flex justify-content-end align-items-center'" + slots + "fB>>" + DT_DOM_FOOTER;

const COLUMNS = Object.freeze({
  statusSync: {
    data: "status_sync",
    title: "Status Sync",
    orderable: false,
    render: (data) => renderStatusSyncBadge(data),
  },
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
  const pageCache = Api.createPageCache();

  function dateInputValue(daysAgo) {
    const d = new Date();
    d.setDate(d.getDate() - daysAgo);
    return d.toISOString().slice(0, 10);
  }

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

  function dateValues(tableId) {
    return { date_from: $(`#${tableId}_date_from`).val(), date_to: $(`#${tableId}_date_to`).val() };
  }

  function exportButton(tableId, exportEndpoint, includeSearch) {
    return {
      text: EXPORT_EXCEL_ICON,
      titleAttr: APP.MESSAGES.EXPORT_EXCEL,
      className: EXPORT_BUTTON_CLASS,
      action: function () {
        const searchValue = includeSearch && tables[tableId] ? tables[tableId].search() : "";
        Api.download(exportEndpoint, { "search[value]": searchValue, ...dateValues(tableId) });
      },
    };
  }

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

  function render(tableId, endpoint, columns, options) {
    const isRecon = options.kind === "recon";
    const withDateFilter = isRecon || !!options.dateFilter;
    const filterParams = () => ({
      ...(isRecon
        ? {
            status_sync: $(`#${tableId}_wrapper .recon-status-filter select`).val() || "",
            so_status: $(`#${tableId}_wrapper .recon-so-status-filter select`).val() || "",
          }
        : {}),
      ...(withDateFilter
        ? {
            date_from: dateValues(tableId).date_from || dateInputValue(APP.DATE_FILTER_MAX_RANGE_DAYS),
            date_to: dateValues(tableId).date_to || dateInputValue(0),
          }
        : {}),
    });
    return new Promise((resolve) => {
      tables[tableId] = $(`#${tableId}`).DataTable({
        serverSide: true,
        processing: true,
        ajax: Api.dataTableSource(endpoint, filterParams, pageCache),
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
          if (withDateFilter) addDateRangeFilter(tableId);
          resolve();
        },
      });
      if (isRecon) addStatusSyncFilter(tableId);
    });
  }

  function load(tableId, endpoint, columns, options) {
    return Loading.wrapPage(() => render(tableId, endpoint, columns, options || {}), APP.MESSAGES.LOADING);
  }

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
