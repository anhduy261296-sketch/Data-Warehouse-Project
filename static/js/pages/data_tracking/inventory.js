/*
 * Data Tracking > Tồn kho SAP-WMS (templates/data_tracking/inventory.html).
 * Tong hop + bieu do, bang doi chieu, popup chung tu tung dong, popup danh sach lech.
 */
const INV_API = ENDPOINTS.dataTracking.inventory;

function inventoryFilterParams() {
  return {
    status_sync: $("#inventoryStatusFilter").val() || "",
    whs_code: $("#inventoryWhsFilter").val() || "",
  };
}

function inventoryBlock(cls, title, headers, rowsHtml, colClass) {
  return `
      <div class="${colClass} mb-3">
        <div class="inv-detail-block ${cls}">
          <div class="inv-detail-title font-weight-bold mb-1">${title}</div>
          <div class="table-responsive"><table class="table table-sm table-bordered mb-0">
            <thead><tr>${headers.map((h) => `<th class="${h.cls || ""}">${h.text}</th>`).join("")}</tr></thead>
            <tbody>${rowsHtml || `<tr><td colspan="${headers.length}" class="text-center text-muted">Không có dữ liệu</td></tr>`}</tbody>
          </table></div>
        </div>
      </div>`;
}

function blockTitle(label, rows, field, totalLabel) {
  const total = rows.reduce((s, r) => s + (r[field] || 0), 0);
  return `${label} · ${totalLabel || "tổng"} ${VN_QTY_FORMAT.format(total)}`;
}

function bothTitle(label, rows) {
  const sap = rows.reduce((s, r) => s + (r.sap_qty || 0), 0);
  const wms = rows.reduce((s, r) => s + (r.wms_qty || 0), 0);
  return `${label} · tổng SAP ${VN_QTY_FORMAT.format(sap)} · tổng WMS ${VN_QTY_FORMAT.format(wms)}`;
}

function diffFormula(payload) {
  const sum = (rows, f) => (rows || []).reduce((s, r) => s + (r[f] || 0), 0);
  const bothSap = sum(payload.both, "sap_qty");
  const bothWms = sum(payload.both, "wms_qty");
  const sapOnly = sum(payload.sap_only, "sap_qty");
  const wmsOnly = sum(payload.wms_only, "wms_qty");
  const f = (v) => VN_QTY_FORMAT.format(v);
  return (
    `Số lượng chênh lệch tổng tồn ` +
    `= | (${f(bothSap)} − ${f(bothWms)}) + ${f(sapOnly)} − ${f(wmsOnly)} | = ${f(Math.abs(bothSap - bothWms + sapOnly - wmsOnly))}`
  );
}

function renderInventoryDetail(payload) {
  const both = payload.both || [];
  const sapOnly = payload.sap_only || [];
  const wmsOnly = payload.wms_only || [];
  const sapDate = (v) => (v ? formatDateTime(v).slice(0, 10) : "—");
  const bothDate = (r) => {
    const sap = sapDate(r.sap_date);
    const wms = sapDate(r.wms_date);
    return sap === wms || wms === "—" ? sap : `${sap}<div class="text-muted small">WMS: ${wms}</div>`;
  };
  const num = (v, bold) => `<td class="text-right nw${bold ? " font-weight-bold" : ""}">${formatAmount(v)}</td>`;
  const docHeaders = [
    { text: "Số chứng từ", cls: "nw" },
    { text: "Ngày chứng từ", cls: "nw" },
    { text: "Loại" },
    { text: "SL (+/-)", cls: "nw" },
  ];
  const bothRows = both
    .map(
      (r) =>
        `<tr${r.diff_qty ? ' class="inv-row-diff"' : ""}><td class="nw">${escapeHtml(r.doc_no)}${r.wms_doc_no ? `<div class="text-muted small">WMS: ${escapeHtml(r.wms_doc_no)}</div>` : ""}</td>` +
        `<td class="nw">${bothDate(r)}</td>` +
        `<td>${escapeHtml(r.doc_type)}${r.wms_doc_type && r.wms_doc_type !== r.doc_type ? `<div class="text-muted small">WMS: ${escapeHtml(r.wms_doc_type)}</div>` : ""}</td>${num(r.sap_qty)}${num(r.wms_qty)}${num(r.diff_qty, true)}</tr>`,
    )
    .join("");
  const sapRows = sapOnly
    .map(
      (r) =>
        `<tr><td class="nw">${escapeHtml(r.doc_no)}</td><td class="nw">${sapDate(r.doc_date)}</td><td>${escapeHtml(r.doc_type)}</td>${num(r.qty, true)}</tr>`,
    )
    .join("");
  const wmsRows = wmsOnly
    .map(
      (r) =>
        `<tr><td class="nw">${escapeHtml(r.doc_no)}</td><td class="nw">${sapDate(r.doc_date)}</td><td>${escapeHtml(r.doc_type)}</td>${num(r.qty, true)}</tr>`,
    )
    .join("");
  const note = payload.truncated ? '<div class="small text-danger mb-2">Mã hàng có quá nhiều chứng từ, chỉ hiển thị một phần.</div>' : "";
  return (
    note +
    '<div class="row">' +
    inventoryBlock(
      "inv-detail-both",
      bothTitle("Chứng từ có ở 2 bên", both),
      [
        { text: "Số chứng từ", cls: "nw" },
        { text: "Ngày", cls: "nw" },
        { text: "Loại" },
        { text: "SAP", cls: "nw" },
        { text: "WMS", cls: "nw" },
        { text: "Lệch", cls: "nw" },
      ],
      bothRows,
      "col-12",
    ) +
    inventoryBlock("inv-detail-sap", blockTitle("SAP có, WMS không có", sapOnly, "qty"), docHeaders, sapRows, "col-lg-6") +
    inventoryBlock("inv-detail-wms", blockTitle("WMS có, SAP không có", wmsOnly, "qty"), docHeaders, wmsRows, "col-lg-6") +
    "</div>"
  );
}

const barValueLabels = {
  id: "barValueLabels",
  afterDatasetsDraw(chart) {
    const { ctx } = chart;
    const dataset = chart.data.datasets[0];
    ctx.save();
    ctx.font = `600 14px ${APP.FONT_FAMILY}`;
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    chart.getDatasetMeta(0).data.forEach((bar, i) => {
      ctx.fillStyle = dataset.labelColors[i];
      ctx.fillText(VN_QTY_FORMAT.format(dataset.data[i]), bar.x, bar.y - 6);
    });
    ctx.restore();
  },
};

function renderInventorySummary(summary) {
  if (!summary) return;
  const sap = summary.sap_total || 0;
  const wms = summary.wms_total || 0;
  const ratio = summary.diff_ratio_pct || 0;
  $("#invWmsTotal").text(VN_QTY_FORMAT.format(wms));
  $("#invSapTotal").text(VN_QTY_FORMAT.format(sap));
  $("#invDiffTotal").text(VN_QTY_FORMAT.format(summary.diff_total || 0));
  $("#invDiffRatio").text(`${VN_PERCENT_FORMAT.format(ratio)}%`);

  if (typeof Chart === "undefined") return;
  const fontsReady =
    document.fonts && document.fonts.load
      ? Promise.all(["400 12px", "500 13px", "600 14px"].map((f) => document.fonts.load(`${f} "Be Vietnam Pro"`)))
      : Promise.resolve();
  fontsReady.catch(() => {}).then(() => drawInventoryCharts(sap, wms, ratio));
}

function drawInventoryCharts(sap, wms, ratio) {
  Chart.defaults.font.family = APP.FONT_FAMILY;
  Chart.defaults.font.size = 13;
  Chart.defaults.color = APP.COLORS.CHART_TEXT;

  const span = Math.max(Math.abs(sap - wms), 1);
  const lo = Math.min(sap, wms) - span * 1.5;
  const hi = Math.max(sap, wms) + span * 1.5;
  const rawStep = (hi - lo) / 5;
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((v) => v >= rawStep);
  const axisMin = Math.max(0, Math.floor(lo / step) * step);
  const axisMax = Math.ceil(hi / step) * step;
  new Chart(document.getElementById("invCompareChart"), {
    type: "bar",
    data: {
      labels: ["SAP", "WMS"],
      datasets: [
        {
          data: [sap, wms],
          backgroundColor: [APP.COLORS.SAP.fill, APP.COLORS.WMS.fill],
          borderColor: [APP.COLORS.SAP.border, APP.COLORS.WMS.border],
          labelColors: [APP.COLORS.SAP.text, APP.COLORS.WMS.text],
          borderWidth: 1.5,
          borderRadius: 10,
          borderSkipped: false,
          maxBarThickness: 80,
        },
      ],
    },
    options: {
      maintainAspectRatio: false,
      layout: { padding: { top: 26 } },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => VN_QTY_FORMAT.format(c.raw) } } },
      scales: {
        y: {
          min: axisMin,
          max: axisMax,
          ticks: { stepSize: step, callback: (v) => VN_QTY_FORMAT.format(v), font: { size: 12 }, padding: 6 },
          afterFit: (scale) => {
            scale.width += 10;
          },
          grid: { color: APP.COLORS.CHART_GRID },
          border: { display: false },
        },
        x: {
          grid: { display: false },
          ticks: { font: { size: 14, weight: "600" }, color: (c) => [APP.COLORS.SAP.text, APP.COLORS.WMS.text][c.index] },
        },
      },
    },
    plugins: [barValueLabels],
  });
  new Chart(document.getElementById("invRatioChart"), {
    type: "pie",
    data: {
      labels: [`Khớp tồn ${VN_PERCENT_FORMAT.format(100 - ratio)}%`, `Lệch tồn ${VN_PERCENT_FORMAT.format(ratio)}%`],
      datasets: [{ data: [100 - ratio, ratio], backgroundColor: [APP.COLORS.MATCH, APP.COLORS.DIFF], borderColor: "#fff", borderWidth: 2 }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "bottom",
          labels: { usePointStyle: true, pointStyle: "circle", padding: 16, font: { size: 13, weight: "500" } },
        },
        tooltip: { callbacks: { label: (c) => `${VN_PERCENT_FORMAT.format(c.raw)}%` } },
      },
    },
  });
}

function renderInventoryDiffList(payload) {
  const both = payload.both || [];
  const sapOnly = payload.sap_only || [];
  const wmsOnly = payload.wms_only || [];
  const num = (v, bold) => `<td class="text-right nw${bold ? " font-weight-bold" : ""}">${formatAmount(v)}</td>`;
  const itemCells = (r) =>
    `<td class="nw">${escapeHtml(r.item_code)}</td><td><span class="inv-name-text" title="${escapeHtml(r.item_name)}">${escapeHtml(r.item_name)}</span></td>` +
    `<td class="nw">${escapeHtml(r.whs_code)}</td><td class="nw">${r.status_item ? escapeHtml(r.status_item) : "—"}</td>`;
  const itemHeaders = [{ text: "Mã hàng", cls: "nw" }, { text: "Tên hàng" }, { text: "Kho" }, { text: "Trạng thái", cls: "nw" }];
  return (
    '<div class="row">' +
    inventoryBlock(
      "inv-detail-both",
      bothTitle("Hai bên có", both),
      [...itemHeaders, { text: "SAP", cls: "nw" }, { text: "WMS", cls: "nw" }, { text: "Lệch", cls: "nw" }],
      both.map((r) => `<tr>${itemCells(r)}${num(r.sap_qty)}${num(r.wms_qty)}${num(r.diff_qty, true)}</tr>`).join(""),
      "col-12",
    ) +
    inventoryBlock(
      "inv-detail-sap",
      blockTitle("SAP có, WMS không có", sapOnly, "sap_qty"),
      [...itemHeaders, { text: "SL", cls: "nw" }],
      sapOnly.map((r) => `<tr>${itemCells(r)}${num(r.sap_qty, true)}</tr>`).join(""),
      "col-lg-6",
    ) +
    inventoryBlock(
      "inv-detail-wms",
      blockTitle("WMS có, SAP không có", wmsOnly, "wms_qty"),
      [...itemHeaders, { text: "SL", cls: "nw" }],
      wmsOnly.map((r) => `<tr>${itemCells(r)}${num(r.wms_qty, true)}</tr>`).join(""),
      "col-lg-6",
    ) +
    "</div>"
  );
}

$(function () {
  const metaRequest = Api.get(INV_API.meta);

  const table = $("#reconInventoryTable").DataTable({
    serverSide: true,
    processing: true,
    ajax: {
      url: `${ENDPOINTS.API_BASE}${INV_API.report}`,
      data: function (d) {
        Object.assign(d, inventoryFilterParams());
      },
    },
    columns: [
      {
        data: "status_sync",
        title: "Đối chiếu",
        render: (data) => `<span class="badge ${APP.INVENTORY_STATUS_BADGE[data] || "badge-light"}">${escapeHtml(data)}</span>`,
      },
      { data: "item_code", title: "Mã hàng" },
      { data: "item_name", title: "Tên hàng" },
      { data: "whs_code", title: "Kho" },
      { data: "whs_name", title: "Tên kho" },
      { data: "status_item", title: "Trạng thái", render: (d) => (d ? escapeHtml(d) : "—") },
      { data: "sap_qty", title: "SAP tồn", className: "text-right", render: (d) => formatAmount(d) },
      { data: "wms_qty", title: "WMS tồn", className: "text-right", render: (d) => formatAmount(d) },
      {
        data: "diff_qty",
        title: "Chênh lệch",
        className: "text-right",
        render: (d) => `<a href="#" class="inv-diff-link font-weight-bold" title="Xem chi tiết phiếu nhập/xuất">${formatAmount(d)}</a>`,
      },
      { data: "uom", title: "ĐVT" },
    ],
    order: [],
    dom:
      "<'row align-items-center'<'col-sm-12 d-flex justify-content-end align-items-center'" +
      "<'inventory-whs-filter mr-2'><'inventory-status-filter mr-2'>fB>>" +
      "<'row'<'col-sm-12't>>" +
      "<'row align-items-center'<'col-sm-6'i>" +
      "<'col-sm-6 d-flex justify-content-end align-items-center'lp>>",
    buttons: [
      {
        text: EXPORT_EXCEL_ICON,
        titleAttr: APP.MESSAGES.EXPORT_EXCEL,
        className: EXPORT_BUTTON_CLASS,
        action: function () {
          Api.download(INV_API.export, { "search[value]": table.search(), ...inventoryFilterParams() });
        },
      },
    ],
    language: { lengthMenu: "_MENU_" },
    initComplete: function () {
      Loading.hide();
    },
  });

  const $status = $(
    '<select id="inventoryStatusFilter" class="form-control form-control-sm" title="Mặc định ẩn: Không quản lý trên WMS">' +
      '<option value="">Tất cả (trừ không quản lý trên WMS)</option></select>',
  );
  const $whs = $('<select id="inventoryWhsFilter" class="form-control form-control-sm"><option value="">Tất cả kho</option></select>');
  $(".inventory-status-filter").append($status);
  $(".inventory-whs-filter").append($whs);
  $status.add($whs).on("change", () => table.draw());

  metaRequest
    .done(function (meta) {
      (meta.statuses || []).forEach((s) => $status.append($("<option>").attr("value", s).text(s)));
      (meta.warehouses || []).forEach((w) =>
        $whs.append(
          $("<option>")
            .attr("value", w.code)
            .text(w.name ? `${w.code} - ${w.name}` : w.code),
        ),
      );
      $(".inventory-snapshot-info").text(
        `Tồn SAP cập nhật ${formatUtcDateTime(meta.sap_snapshot_at)} · ` +
          `Tồn WMS cập nhật ${formatUtcDateTime(meta.wms_snapshot_at)} · ` +
          `Đối chiếu cập nhật ${formatUtcDateTime(meta.recon_refreshed_at)}`,
      );
      renderInventorySummary(meta.summary);
    })
    .fail(function () {
      $(".inventory-snapshot-info").text("Không tải được thông tin cập nhật.");
    });

  $("#inventoryDiffExport").attr("href", Api.url(INV_API.diffExport)).html(`${EXPORT_EXCEL_ICON}<span class="ml-1">Xuất Excel</span>`);
  $("#inventoryDetailExport").html(`${EXPORT_EXCEL_ICON}<span class="ml-1">Xuất Excel</span>`);

  function applyModalSearch($modal) {
    const term = normalizeSearchText($modal.find(".inv-modal-search").val()).trim();
    $modal.find(".modal-body tbody tr").each(function () {
      const $tr = $(this);
      if ($tr.children("td[colspan]").length) return;
      $tr.toggle(!term || normalizeSearchText($tr.text()).includes(term));
    });
  }
  $(".inv-modal-search").on("input", function () {
    applyModalSearch($(this).closest(".modal"));
  });

  let diffListRequest = null;
  $("#invDiffCard").on("click", function (e) {
    e.preventDefault();
    $("#inventoryDiffModal").modal("show");
    if (diffListRequest) return;
    $("#inventoryDiffBody").html('<div class="text-muted p-3 text-center">Đang tải danh sách lệch...</div>');
    diffListRequest = Api.get(INV_API.diffList)
      .done((payload) => {
        $("#inventoryDiffSummary").text(diffFormula(payload));
        $("#inventoryDiffBody").html(renderInventoryDiffList(payload));
        applyModalSearch($("#inventoryDiffModal"));
      })
      .fail(() => {
        diffListRequest = null;
        $("#inventoryDiffBody").html('<div class="text-danger p-3">Không tải được danh sách lệch.</div>');
      });
  });

  let detailRequestId = 0;
  $("#reconInventoryTable tbody").on("click", "a.inv-diff-link", function (e) {
    e.preventDefault();
    const data = table.row($(this).closest("tr")).data();
    if (!data) return;
    const requestId = ++detailRequestId;
    $("#inventoryDetailTitle").text(`${data.item_code} - ${data.item_name || ""}`);
    $("#inventoryDetailSummary").text(
      `Kho ${data.whs_code}${data.whs_name ? " - " + data.whs_name : ""} · Trạng thái ${data.status_item || "—"} · ` +
        `SAP tồn ${formatAmount(data.sap_qty)} · WMS tồn ${formatAmount(data.wms_qty)} · Chênh lệch ${formatAmount(data.diff_qty)}`,
    );
    $("#inventoryDetailBody").html('<div class="text-muted p-3 text-center">Đang tải chi tiết...</div>');
    $("#inventoryDetailModal").find(".inv-modal-search").val("");
    const detailParams = { item_code: data.item_code, whs_code: data.whs_code, status_item: data.status_item || "" };
    $("#inventoryDetailExport").attr("href", Api.url(INV_API.detailExport, detailParams));
    $("#inventoryDetailModal").modal("show");
    Api.get(INV_API.detail, detailParams)
      .done((payload) => {
        if (requestId === detailRequestId) $("#inventoryDetailBody").html(renderInventoryDetail(payload));
      })
      .fail(() => {
        if (requestId === detailRequestId) $("#inventoryDetailBody").html('<div class="text-danger p-3">Không tải được chi tiết.</div>');
      });
  });
});
