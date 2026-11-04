(function () {
  const EP = ENDPOINTS.messaging;
  const cache = Api.createPageCache();
  // Lấy ngày theo giờ máy người dùng: toISOString là UTC, trước 7h sáng sẽ lùi về hôm qua và ẩn log mới.
  const dayValue = (daysAgo) => {
    const d = new Date();
    d.setDate(d.getDate() - daysAgo);
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  };
  const setDefaultDates = () => {
    $("#znsLogFrom").val(dayValue(APP.DATE_FILTER_MAX_RANGE_DAYS));
    $("#znsLogTo").val(dayValue(0));
  };
  setDefaultDates();

  const filters = () => ({
    date_from: $("#znsLogFrom").val(),
    date_to: $("#znsLogTo").val(),
    department: $("#znsLogDepartment").val(),
    actor: $("#znsLogActor").val().trim(),
    q: $("#znsLogSearch").val().trim(),
  });

  const table = $("#znsLogTable").DataTable({
    ...pagedTableOptions(),
    serverSide: true,
    processing: true,
    ajax: Api.dataTableSource(EP.logs, filters, cache),
    language: { ...pagedTableOptions().language, emptyTable: "Không có nhật ký phù hợp" },
    columns: [
      { data: "created_at", className: "text-nowrap", render: (v) => formatUtcDate(v) },
      { data: "actor", className: "text-nowrap", render: (v) => escapeHtml(v) },
      { data: "action_label", render: (v) => escapeHtml(v) },
      { data: "target_label", className: "text-nowrap", render: (v) => escapeHtml(v || "—") },
      { data: "department_name", className: "text-nowrap", render: (v) => escapeHtml(v || "—") },
      { data: "detail", className: "zns-log-detail", render: (v) => escapeHtml(v || "") },
      { data: "ip_address", className: "text-nowrap", render: (v) => escapeHtml(v || "—") },
    ],
  });

  const reload = () => table.ajax.reload(null, true);
  let typing = null;
  $("#znsLogFrom, #znsLogTo, #znsLogDepartment").on("change", reload);
  $("#znsLogActor, #znsLogSearch").on("input", () => {
    clearTimeout(typing);
    typing = setTimeout(reload, 300);
  });
  $("#znsLogReload").on("click", () => {
    cache.clear();
    table.ajax.reload(null, false);
  });
  $("#znsLogReset").on("click", () => {
    $("#znsLogDepartment, #znsLogActor, #znsLogSearch").val("");
    setDefaultDates();
    cache.clear();
    reload();
  });
  $("#znsLogExport").on("click", () => Api.download(EP.logsExport, filters()));
})();
