let systemsTrackingTable = null;

function loadSystemsTracking() {
  return Loading.wrapPage(renderSystemsTracking, "Đang tải dữ liệu...");
}

async function renderSystemsTracking() {
  const url = `${CONFIG.API_BASE}${CONFIG.SYSTEMS_TRACKING_REPORT}`;
  const payload = await fetchJson(url);
  const rows = payload.data || [];

  if (systemsTrackingTable) {
    systemsTrackingTable.clear();
    systemsTrackingTable.rows.add(rows);
    systemsTrackingTable.draw();
    return;
  }

  systemsTrackingTable = $("#systemsTrackingTable").DataTable({
    data: rows,
    columns: [
      { data: "name" },
      { data: "status" },
      {
        data: "last_seen",
        render: function (data) {
          return formatDateTime(data);
        },
      },
      {
        data: "updated_at",
        render: function (data) {
          return formatDateTime(data);
        },
      },
    ],
  });
}
