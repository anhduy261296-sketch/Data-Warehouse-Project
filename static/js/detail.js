


$(document).on("show.bs.dropdown", ".dt-buttons", function () {
  $(this).closest(".table-responsive").css("overflow", "visible");
});
$(document).on("hide.bs.dropdown", ".dt-buttons", function () {
  $(this).closest(".table-responsive").css("overflow", "auto");
});






const detailTables = {};

function loadDetailTable(tableId, endpoint, columns, exportEndpoint, options = {}) {
  return Loading.wrapPage(
    () => renderDetailTable(tableId, endpoint, columns, exportEndpoint, options),
    "Đang tải dữ liệu...",
  );
}









const DATE_FILTER_MAX_RANGE_DAYS = 30;

function _dateInputValue(daysAgo) {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  return d.toISOString().slice(0, 10);
}

function _detailOrReconTable(tableId) {
  return (typeof detailTables !== "undefined" && detailTables[tableId]) ||
    (typeof reconTables !== "undefined" && reconTables[tableId]);
}

function addDateRangeFilter(tableId) {
  const $slot = $(`#${tableId}_wrapper .detail-date-filter`);
  $slot.html(`
    <div class="d-flex align-items-center">
      <label class="mb-0 mr-1 small text-muted">Từ ngày</label>
      <input type="date" class="form-control form-control-sm mr-2" id="${tableId}_date_from" style="width: 150px;">
      <label class="mb-0 mr-1 small text-muted">Đến ngày</label>
      <input type="date" class="form-control form-control-sm mr-2" id="${tableId}_date_to" style="width: 150px;">
      <button type="button" class="btn btn-sm btn-primary" id="${tableId}_date_search">Tìm</button>
    </div>
  `);
  const $from = $(`#${tableId}_date_from`);
  const $to = $(`#${tableId}_date_to`);
  $from.val(_dateInputValue(DATE_FILTER_MAX_RANGE_DAYS));
  $to.val(_dateInputValue(0));

  function clampRange(changedField) {
    const fromDate = new Date($from.val());
    const toDate = new Date($to.val());
    if (isNaN(fromDate) || isNaN(toDate)) return;
    const diffDays = Math.round((toDate - fromDate) / 86400000);
    if (diffDays > DATE_FILTER_MAX_RANGE_DAYS) {
      
      
      if (changedField === "from") {
        const cappedTo = new Date(fromDate);
        cappedTo.setDate(cappedTo.getDate() + DATE_FILTER_MAX_RANGE_DAYS);
        $to.val(cappedTo.toISOString().slice(0, 10));
      } else {
        const cappedFrom = new Date(toDate);
        cappedFrom.setDate(cappedFrom.getDate() - DATE_FILTER_MAX_RANGE_DAYS);
        $from.val(cappedFrom.toISOString().slice(0, 10));
      }
    } else if (diffDays < 0) {
      
      
      $to.val($from.val());
    }
  }

  
  
  
  
  
  $from.on("change", function () {
    clampRange("from");
    _detailOrReconTable(tableId).draw();
  });
  $to.on("change", function () {
    clampRange("to");
    _detailOrReconTable(tableId).draw();
  });
  $(`#${tableId}_date_search`).on("click", function () {
    clampRange("to");
    _detailOrReconTable(tableId).draw();
  });

  
  
  
  
  
  
  
}












const EXPORT_EXCEL_ICON = `
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V8l-3-6Z" fill="#F1F8F4" stroke="#1D6F42" stroke-width="1.4"/>
    <path d="M14 2v4a2 2 0 0 0 2 2h3" stroke="#1D6F42" stroke-width="1.4" stroke-linejoin="round"/>
    <path d="M9.5 13.5v5.5m0 0l-2.2-2.2m2.2 2.2l2.2-2.2" stroke="#1D6F42" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>
`;

function exportButtonConfig(tableId, exportEndpoint) {
  return {
    text: EXPORT_EXCEL_ICON,
    titleAttr: "Xuất Excel",
    
    
    
    className:
      "btn btn-sm bg-white border shadow-sm d-inline-flex " +
      "align-items-center justify-content-center detail-export-btn",
    action: function () {
      const dt = detailTables[tableId];
      const searchValue = dt ? dt.search() : "";
      const url = new URL(`${CONFIG.API_BASE}${exportEndpoint}`, window.location.origin);
      if (searchValue) {
        url.searchParams.set("search[value]", searchValue);
      }
      const dateFrom = $(`#${tableId}_date_from`).val();
      const dateTo = $(`#${tableId}_date_to`).val();
      if (dateFrom) url.searchParams.set("date_from", dateFrom);
      if (dateTo) url.searchParams.set("date_to", dateTo);
      window.location.href = url.toString();
    },
  };
}

function renderDetailTable(tableId, endpoint, columns, exportEndpoint, options = {}) {
  return new Promise((resolve) => {
    detailTables[tableId] = $(`#${tableId}`).DataTable({
      serverSide: true,
      processing: true,
      ajax: {
        url: `${CONFIG.API_BASE}${endpoint}`,
        data: function (d) {
          if (options.dateFilter) {
            d.date_from = $(`#${tableId}_date_from`).val() || "";
            d.date_to = $(`#${tableId}_date_to`).val() || "";
          }
        },
      },
      columns: columns,
      order: [],
      
      
      
      
      
      
      
      
      
      
      dom:
        "<'row align-items-center'<'col-sm-12 d-flex justify-content-end align-items-center'" +
        "<'detail-date-filter mr-2'>fB>>" +
        "<'row'<'col-sm-12't>>" +
        "<'row align-items-center'<'col-sm-6'i>" +
        "<'col-sm-6 d-flex justify-content-end align-items-center'lp>>",
      buttons: [
        {
          
          
          
          
          
          
          extend: "colvis",
          text: '<i class="fas fa-cog"></i>',
          titleAttr: "Chọn cột hiển thị",
          className: "btn btn-sm btn-outline-secondary detail-colvis-btn",
          
          
          
          align: "button-right",
          prefixButtons: [
            {
              text: "Chọn tất cả",
              action: function (e, dt, node) {
                const stillHidden = dt.columns(":hidden").count() > 0;
                if (stillHidden) {
                  dt.columns(":hidden").visible(true);
                  $(node).text("Hủy chọn tất cả");
                } else {
                  
                  
                  
                  columns.forEach((col, idx) => {
                    if (col.visible === false) {
                      dt.column(idx).visible(false);
                    }
                  });
                  $(node).text("Chọn tất cả");
                }
              },
            },
          ],
        },
        
        
        ...(exportEndpoint ? [exportButtonConfig(tableId, exportEndpoint)] : []),
      ],
      language: { lengthMenu: "_MENU_" },
      initComplete: function () {
        
        
        
        
        if (options.dateFilter) {
          addDateRangeFilter(tableId);
          detailTables[tableId].draw();
        }
        resolve();
      },
    });
  });
}

const DETAIL_STATUS_SYNC_COLUMN = {
  data: "status_sync",
  title: "Status Sync",
  orderable: false,
  render: function (data) {
    
    
    
    if (!data) {
      return '<span class="badge badge-secondary">Chưa đối soát</span>';
    }
    return renderStatusSyncBadge(data);
  },
};

const DETAIL_AMOUNT_COLUMN = (field, title, visible = true) => ({
  data: field,
  title: title,
  className: "text-right",
  visible: visible,
  render: function (data) {
    return formatAmount(data);
  },
});

const DETAIL_DATETIME_COLUMN = (field, title, visible = true) => ({
  data: field,
  title: title,
  visible: visible,
  render: function (data) {
    return formatDateTime(data);
  },
});
