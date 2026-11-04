(function () {
  const EP = ENDPOINTS.messaging;
  const STATUS = { sent: "#0ca30c", unknown: "#fab219", failed: "#d03b3b" };
  const VOLUME = "#4e73df";
  const $report = $("#znsReport");
  let seq = 0;

  const setDefaultDates = () => {
    $("#znsReportFrom").val(dayInputValue(APP.DATE_FILTER_MAX_RANGE_DAYS));
    $("#znsReportTo").val(dayInputValue(0));
  };
  const filters = () => ({
    date_from: $("#znsReportFrom").val(),
    date_to: $("#znsReportTo").val(),
    owner: $("#znsReportOwner").val(),
    department: $("#znsReportDepartment").val(),
    template: $("#znsReportTemplate").val(),
  });

  const rate = (v) => (v === null || v === undefined ? "—" : `${String(v).replace(".", ",")}%`);

  function renderKpis(s) {
    const tiles = [
      ["fa-layer-group", "Số lô", s.batches || 0, "Lô đã xác nhận gửi"],
      ["fa-users", "Lượt khách", s.total, `${formatAmount(s.phones)} số điện thoại khác nhau`],
      ["fa-check-circle", "Incom đã nhận", s.sent, `Tỷ lệ ${rate(s.rate)}`],
      ["fa-question-circle", "Chưa rõ", s.unknown, "Không biết tin đã đi hay chưa"],
      ["fa-times-circle", "Thất bại", s.failed, "Incom từ chối hoặc gọi không được"],
      ["fa-file-excel", "Dòng lỗi dữ liệu", s.invalid, "Không gửi, không tính vào lượt khách"],
    ];
    $("#znsReportKpis").html(
      tiles
        .map(
          ([icon, label, value, note]) => `<div class="rpt-card zns-report-kpi">
            <div class="zns-report-kpi-label"><i class="fas ${icon} mr-1"></i>${label}</div>
            <div class="zns-report-kpi-value">${formatAmount(value)}</div>
            <div class="zns-report-kpi-note">${escapeHtml(note)}</div>
          </div>`,
        )
        .join(""),
    );
  }

  function renderDaily(daily) {
    const hasData = daily.some((d) => d.total > 0);
    $("#znsReportCharts").toggleClass("d-none", !hasData);
    $("#znsReportDailyEmpty").toggleClass("d-none", hasData);
    if (!hasData) return;
    const labels = daily.map((d) => `${d.day.slice(8, 10)}/${d.day.slice(5, 7)}`);
    // Cố định bề rộng trục tung để cột của 2 biểu đồ thẳng hàng theo ngày.
    const yAxis = (extra) => ({ beginAtZero: true, grid: { color: APP.COLORS.CHART_GRID }, afterFit: (axis) => (axis.width = 52), ...extra });
    const xAxis = { grid: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 12 } };
    ChartKit.render("znsReportVolume", {
      type: "bar",
      data: {
        labels,
        // Ngày không gửi để trống: minBarLength sẽ vẽ cả giá trị 0 thành cột.
        datasets: [{ label: "Lượt khách", data: daily.map((d) => d.total || null), backgroundColor: VOLUME, borderRadius: 2, maxBarThickness: 28, minBarLength: 4 }],
      },
      options: {
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (c) => `Lượt khách: ${formatAmount(c.raw)}` } },
        },
        scales: { x: xAxis, y: yAxis({ ticks: { precision: 0, callback: (v) => formatAmount(v) } }) },
      },
    });
    const called = (d) => d.sent + d.unknown + d.failed;
    const series = (key, label) => ({
      label,
      data: daily.map((d) => (called(d) ? Math.round((d[key] * 1000) / called(d)) / 10 : null)),
      counts: daily.map((d) => d[key]),
      backgroundColor: STATUS[key],
      borderColor: "#fff",
      borderWidth: { top: 2 },
      maxBarThickness: 28,
    });
    ChartKit.render("znsReportShare", {
      type: "bar",
      data: { labels, datasets: [series("sent", "Incom đã nhận"), series("unknown", "Chưa rõ"), series("failed", "Thất bại")] },
      options: {
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 12 } },
          tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${rate(c.raw)} (${formatAmount(c.dataset.counts[c.dataIndex])} khách)` } },
        },
        scales: {
          x: { ...xAxis, stacked: true },
          y: yAxis({ stacked: true, max: 100, ticks: { stepSize: 25, callback: (v) => `${v}%` } }),
        },
      },
    });
  }

  const COUNT_COLUMNS = [
    ["Số lô", (r) => formatAmount(r.batches)],
    ["Lượt khách", (r) => formatAmount(r.total)],
    ["Incom đã nhận", (r) => formatAmount(r.sent)],
    ["Chưa rõ", (r) => formatAmount(r.unknown)],
    ["Thất bại", (r) => formatAmount(r.failed)],
    ["Tỷ lệ nhận", (r) => rate(r.rate)],
  ];

  function renderTable(selector, columns, data, emptyText) {
    const head = columns.map(([title]) => `<th>${title}</th>`).join("");
    const body = data.length
      ? data.map((r) => `<tr>${columns.map(([, cell]) => `<td>${cell(r)}</td>`).join("")}</tr>`).join("")
      : `<tr><td colspan="${columns.length}" class="text-muted">${emptyText}</td></tr>`;
    $(selector).html(`<thead><tr>${head}</tr></thead><tbody>${body}</tbody>`);
  }

  function render(d) {
    renderKpis(d.summary);
    renderDaily(d.daily);
    renderTable(
      "#znsReportTemplates",
      [
        ["Mã", (r) => escapeHtml(r.zns_code || "—")],
        ["Tên mẫu", (r) => escapeHtml(r.name || "—")],
        ["Chủ hàng", (r) => escapeHtml(r.owner)],
        ...COUNT_COLUMNS,
      ],
      d.templates,
      "Không có dữ liệu",
    );
    renderTable("#znsReportDepartments", [["Phòng ban", (r) => escapeHtml(r.name)], ...COUNT_COLUMNS], d.departments, "Không có dữ liệu");
    renderTable("#znsReportUsers", [["Người gửi", (r) => escapeHtml(r.name || "—")], ...COUNT_COLUMNS], d.users, "Không có dữ liệu");
    renderTable(
      "#znsReportErrors",
      [
        ["Loại lỗi", (r) => escapeHtml(r.kind_label)],
        ["Nội dung lỗi", (r) => escapeHtml(r.message || "—")],
        ["Số khách", (r) => formatAmount(r.count)],
        ["Số lô", (r) => formatAmount(r.batches)],
      ],
      d.errors,
      "Không có lỗi trong khoảng đã chọn",
    );
  }

  function load() {
    const current = ++seq;
    $report.addClass("is-busy");
    Api.get(EP.report, filters())
      .done((d) => current === seq && render(d))
      .fail((x) => current === seq && Toast.error(Api.errorMessage(x, APP.MESSAGES.LOAD_FAILED_RETRY)))
      .always(() => current === seq && $report.removeClass("is-busy"));
  }

  $("#znsReportFrom, #znsReportTo, #znsReportOwner, #znsReportDepartment, #znsReportTemplate").on("change", load);
  $("#znsReportReload").on("click", load);
  $("#znsReportReset").on("click", () => {
    $("#znsReportOwner, #znsReportDepartment, #znsReportTemplate").val("");
    setDefaultDates();
    load();
  });
  $("#znsReportExport").on("click", () => Api.download(EP.reportExport, filters()));

  setDefaultDates();
  load();
})();
