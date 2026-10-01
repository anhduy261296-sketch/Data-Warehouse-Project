








const reconTables = {};

function loadReconTable(tableId, endpoint, columns, exportEndpoint) {
  return Loading.wrapPage(
    () => renderReconTable(tableId, endpoint, columns, exportEndpoint),
    "Đang tải dữ liệu...",
  );
}

function renderReconTable(tableId, endpoint, columns, exportEndpoint) {
  return new Promise((resolve) => {
    reconTables[tableId] = $(`#${tableId}`).DataTable({
      serverSide: true,
      processing: true,
      ajax: {
        url: `${CONFIG.API_BASE}${endpoint}`,
        data: function (d) {
          d.status_sync = $(`#${tableId}_wrapper .recon-status-filter select`).val() || "";
          
          
          
          d.so_status = $(`#${tableId}_wrapper .recon-so-status-filter select`).val() || "";
          
          
          
          d.date_from = $(`#${tableId}_date_from`).val() || "";
          d.date_to = $(`#${tableId}_date_to`).val() || "";
        },
      },
      columns: columns,
      order: [],
      
      
      
      
      
      
      
      
      
      
      
      dom:
        "<'row align-items-center'<'col-sm-12 d-flex justify-content-end align-items-center'" +
        "<'detail-date-filter mr-2'><'recon-so-status-filter mr-2'><'recon-status-filter mr-2'>fB>>" +
        "<'row'<'col-sm-12't>>" +
        "<'row align-items-center'<'col-sm-6'i>" +
        "<'col-sm-6 d-flex justify-content-end align-items-center'lp>>",
      
      
      
      buttons: exportEndpoint ? [exportButtonConfig(tableId, exportEndpoint)] : [],
      
      
      language: {
        lengthMenu: "_MENU_",
      },
      initComplete: function () {
        addDateRangeFilter(tableId);
        reconTables[tableId].draw();
        resolve();
      },
    });

    addStatusSyncFilter(tableId);
  });
}





function addStatusSyncFilter(tableId) {
  const table = reconTables[tableId];
  const $select = $(
    '<select class="form-control form-control-sm">' +
      '<option value="">Tất cả</option>' +
      '<option value="Sync">Sync</option>' +
      '<option value="Not Sync">Not Sync</option>' +
      "</select>"
  );
  $select.on("change", function () {
    table.draw();
  });
  $(`#${tableId}_wrapper`).find(".recon-status-filter").append($select);
}





function addSoStatusFilter(tableId, optionsEndpoint) {
  const table = reconTables[tableId];
  const $select = $('<select class="form-control form-control-sm"><option value="">Tất cả</option></select>');
  $select.on("change", function () {
    table.draw();
  });
  $(`#${tableId}_wrapper`).find(".recon-so-status-filter").append($select);

  $.getJSON(`${CONFIG.API_BASE}${optionsEndpoint}`, function (payload) {
    (payload.options || []).forEach(function (value) {
      $select.append($("<option>").attr("value", value).text(value));
    });
  });
}

const RECON_AMOUNT_COLUMN = (field, title) => ({
  data: field,
  title: title,
  className: "text-right",
  render: function (data) {
    return formatAmount(data);
  },
});

const RECON_STATUS_SYNC_COLUMN = {
  data: "status_sync",
  title: "Status Sync",
  orderable: false,
  render: function (data) {
    return renderStatusSyncBadge(data);
  },
};

const RECON_REFRESHED_AT_COLUMN = {
  data: "refreshed_at",
  title: "Cập nhật lúc",
  render: function (data) {
    return formatDateTime(data);
  },
};
