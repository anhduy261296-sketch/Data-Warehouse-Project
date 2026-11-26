(function () {
  const RPT = ENDPOINTS.reports.dms;
  const esc = escapeHtml;
  const money = (value) => formatAmount(value === null || value === undefined || value === "" ? value : Math.round(value));
  const moneyMillions = (value) => new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 }).format((Number(value) || 0) / 1000000);
  const CUSTOM = "custom";
  const BLUE_LIGHT = "rgba(59, 130, 246, 0.35)";
  const NAVY = "#1e3a8a";
  let meta = { months: [], max_range_days: 30 };
  let ordersTable = null;

  function iso(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  }
  function todayVn() {
    return new Date(new Date().toLocaleString("en-US", { timeZone: APP.TIMEZONE }));
  }
  function monthRange(value) {
    const [year, month] = value.split("-").map(Number);
    const last = new Date(year, month, 0);
    const today = todayVn();
    return { date_from: `${value}-01`, date_to: iso(last < today ? last : today) };
  }
  function period() {
    const selected = $("#dmPeriod").val();
    return selected === CUSTOM ? { date_from: $("#dmFrom").val(), date_to: $("#dmTo").val() } : selected ? monthRange(selected) : {};
  }
  function filters() {
    return {
      ...period(),
      document_type: $("#dmType").val(),
      state_code: $("#dmState").val(),
      order_type: $("#dmOrderType").val(),
      source_warehouse_code: $("#dmWarehouse").val(),
    };
  }
  function validPeriod() {
    const { date_from: from, date_to: to } = period();
    let message = "";
    if (!from || !to) message = "Chọn đủ Từ ngày và Đến ngày.";
    else if (from > to) message = "Từ ngày phải trước Đến ngày.";
    else if ((new Date(to) - new Date(from)) / 86400000 > meta.max_range_days)
      message = `Khoảng ngày tối đa ${meta.max_range_days + 1} ngày. Xem dài hơn: chọn từng tháng.`;
    $("#dmFilterError").text(message).toggleClass("d-none", !message);
    return !message;
  }

  function addOptions(selector, values, valueOf, labelOf, current) {
    const $select = $(selector).empty().append($("<option>").val("").text("Tất cả"));
    values.forEach((item) => $select.append($("<option>").val(valueOf(item)).text(labelOf(item))));
    $select.val($select.find(`option[value="${current}"]`).length ? current : "");
  }
  function applyMeta(data) {
    meta = data;
    const $period = $("#dmPeriod");
    const selectedPeriod = $period.val();
    $period.empty();
    data.months.forEach((month) =>
      $period.append($("<option>").val(month.value).text(`Tháng ${month.value.slice(5)}/${month.value.slice(0, 4)}`)),
    );
    $period.append($("<option>").val(CUSTOM).text("Khoảng ngày..."));
    $period.val(selectedPeriod && $period.find(`option[value="${selectedPeriod}"]`).length ? selectedPeriod : data.months.length ? data.months[0].value : CUSTOM);
    addOptions("#dmType", data.document_types, (value) => value, (value) => value, $("#dmType").val());
    addOptions("#dmState", data.states, (item) => item.code, (item) => item.name, $("#dmState").val());
    addOptions("#dmOrderType", data.order_types, (value) => value, (value) => value, $("#dmOrderType").val());
    addOptions(
      "#dmWarehouse",
      data.warehouses,
      (item) => item.code,
      (item) => item.name && item.name !== item.code ? `${item.code} - ${item.name}` : item.code,
      $("#dmWarehouse").val(),
    );
    $("#dmUpdated").text(formatUtcDateTime(data.updated_at));
    toggleCustom();
  }
  function toggleCustom() {
    const custom = $("#dmPeriod").val() === CUSTOM;
    $(".ec-custom").toggleClass("d-none", !custom);
    if (custom && !$("#dmFrom").val()) {
      const range = meta.months[0] ? monthRange(meta.months[0].value) : { date_from: iso(todayVn()), date_to: iso(todayVn()) };
      $("#dmFrom").val(range.date_from);
      $("#dmTo").val(range.date_to);
    }
  }

  const pageCache = Api.createPageCache();
  function setBusy(busy) {
    $("#dmSearch, #dmRefresh").prop("disabled", busy);
    $("#dmOrdersExport").toggleClass("disabled", busy).attr("aria-disabled", busy ? "true" : null);
    $("#dmSearch").html(busy ? '<span class="spinner-border spinner-border-sm mr-1"></span> Đang tải...' : '<i class="fas fa-search mr-1"></i> Xem báo cáo');
  }
  const loader = ReportLoader.create({ setBusy, lockAlways: true });
  const { begin, end } = loader;
  function area(ids, path, render) {
    return loader.area(ids, path, filters(), render);
  }
  function emptyHtml(columns) {
    return `<tr><td colspan="${columns}" class="text-center text-muted">${APP.MESSAGES.NO_DATA}</td></tr>`;
  }

  function loadKpi() {
    return area(["#dmKpis"], RPT.kpi, (data) => {
      $("[data-kpi='amount_short']").text(formatMoneyShort(data.amount_total, 2));
      $("[data-kpi='amount_total']").text(`${money(data.amount_total)} đ`);
      ["total_orders", "sale_orders", "customers", "new_orders", "processing_orders", "success_orders", "cancel_orders", "return_orders"].forEach((key) =>
        $(`[data-kpi="${key}"]`).text(money(data[key])),
      );
      ["new", "processing", "success", "cancel", "return"].forEach((key) =>
        $(`[data-kpi="${key}_rate"]`).text(formatRate(data[`${key}_rate`])),
      );
      $("[data-kpi='avg_order_value']").text(formatMoneyShort(data.avg_order_value, 2));
      $("[data-kpi='avg_sku_per_order']").text(formatQty(data.avg_sku_per_order));
      $("[data-kpi='avg_qty_per_order']").text(formatQty(data.avg_qty_per_order));
    });
  }
  function loadDaily() {
    return area(["#dmDaily"], RPT.daily, (result) => {
      ChartKit.render("dmDailyChart", {
        data: {
          labels: result.data.map((row) => `${row.day.slice(8, 10)}/${row.day.slice(5, 7)}`),
          datasets: [
            {
              type: "line",
              label: "Số đơn hàng",
              data: result.data.map((row) => row.orders),
              yAxisID: "y1",
              borderColor: NAVY,
              backgroundColor: NAVY,
              pointRadius: 3,
              tension: 0.25,
            },
            {
              type: "bar",
              label: "Giá trị",
              data: result.data.map((row) => row.amount_total),
              yAxisID: "y",
              backgroundColor: BLUE_LIGHT,
              borderRadius: 4,
              maxBarThickness: 26,
            },
          ],
        },
        options: {
          maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          plugins: {
            legend: { position: "bottom", labels: { boxWidth: 12 } },
            tooltip: {
              callbacks: {
                label: (context) => (context.dataset.yAxisID === "y" ? `Giá trị: ${money(context.raw)}` : `Đơn hàng: ${money(context.raw)}`),
              },
            },
          },
          scales: {
            y: { ticks: { callback: (value) => formatMoneyShort(value, 1) }, grid: { color: APP.COLORS.CHART_GRID }, title: { display: true, text: "Giá trị" } },
            y1: { position: "right", grid: { display: false }, ticks: { precision: 0 }, title: { display: true, text: "Đơn hàng" } },
            x: { grid: { display: false }, ticks: { font: { size: 10 }, maxRotation: 0, autoSkip: true } },
          },
        },
      });
    });
  }
  function loadBySale() {
    return area(["#dmSale", "#dmSaleDocs"], RPT.bySale, (result) => {
      const byRevenue = result.data
        .filter((row) => row.amount_total || row.orders)
        .sort((a, b) => b.amount_total - a.amount_total || (a.salesperson || "").localeCompare(b.salesperson || ""))
        .slice(0, 5);
      const byOrders = result.data
        .filter((row) => row.amount_total || row.orders)
        .sort((a, b) => b.orders - a.orders || (a.salesperson || "").localeCompare(b.salesperson || ""))
        .slice(0, 5);
      const render = (id, rows, valueKey, format, label) =>
        ChartKit.render(id, {
          type: "bar",
          plugins: [ChartKit.valueLabels],
          data: {
            labels: rows.map((row) => row.salesperson),
            datasets: [
              {
                data: rows.map((row) => row[valueKey]),
                backgroundColor: rows.map((_, i) => APP.COLORS.PASTEL[i % APP.COLORS.PASTEL.length]),
                borderRadius: 6,
                maxBarThickness: 38,
              },
            ],
          },
          options: {
            indexAxis: "y",
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false },
              valueLabels: { format: (value) => (valueKey === "amount_total" ? formatMoneyShort(value, 1) : money(value)) },
              tooltip: {
                callbacks: {
                  label: (context) => `${label}: ${money(context.raw)}${valueKey === "amount_total" ? " đ" : ""}`,
                },
              },
            },
            scales: {
              x: { beginAtZero: true, grace: "15%", ticks: { callback: (value) => format(value) }, grid: { color: APP.COLORS.CHART_GRID } },
              y: { grid: { display: false }, ticks: { font: { size: 12 }, autoSkip: false } },
            },
          },
        });
      render("dmSaleChart", byRevenue, "amount_total", (value) => formatMoneyShort(value, 1), "Giá trị");
      render("dmSaleDocsChart", byOrders, "orders", money, "Đơn hàng");
    });
  }
  function loadTopCustomers() {
    return area(["#dmTopAmount", "#dmTopDocuments"], RPT.topCustomers, (result) => {
      const render = (selector, rows) =>
        $(selector).html(
          rows.length
            ? rows.map((row, index) => `<tr><td>${index + 1}</td><td title="${esc(row.partner_code)}">${esc(row.partner_code)}</td><td title="${esc(row.partner_name)}">${esc(row.partner_name)}</td><td title="Số đơn hàng: ${money(row.orders)}">${money(row.orders)}</td><td title="Giá trị đơn hàng: ${money(row.amount_total)} đ">${moneyMillions(row.amount_total)}</td></tr>`).join("")
            : emptyHtml(5),
        );
      render("#dmTopAmount tbody", result.by_amount || []);
      render("#dmTopDocuments tbody", result.by_orders || []);
    });
  }

  let ordersFilters = {};
  function buildOrdersTable() {
    ordersTable = $("#dmOrdersTable").DataTable({
      serverSide: true,
      processing: true,
      searchDelay: 500,
      pageLength: APP.DATATABLE.PAGE_LENGTH,
      dom: "<'table-responsive'tr><'d-flex justify-content-between align-items-center flex-wrap mt-2'i<'d-flex align-items-center rpt-pager'lp>>",
      order: [[0, "desc"]],
      ajax: Api.dataTableSource(RPT.orders, () => ordersFilters, pageCache),
      columns: [
        { data: "document_date", title: "Ngày đơn hàng", className: "text-nowrap", render: (value) => (value ? `${value.slice(8, 10)}/${value.slice(5, 7)}/${value.slice(0, 4)} ${value.slice(11, 16)}` : "") },
        { data: "document_type", title: "Mã loại đơn DMS", render: (value) => esc(value) },
        { data: "document_code", title: "Mã đơn hàng", className: "text-nowrap", render: (value) => esc(value) },
        { data: "order_type", title: "Loại đơn", render: (value) => esc(value) },
        { data: "partner_code", title: "Mã khách hàng", render: (value) => esc(value) },
        { data: "partner_name", title: "Tên khách hàng", className: "text-nowrap", render: (value) => esc(value) },
        { data: "source_warehouse_code", title: "Mã kho", width: "100px", className: "text-nowrap", render: (value) => esc(value) },
        { data: "salesperson", title: "Sale", width: "200px", className: "text-nowrap", render: (value) => esc(value) },
        { data: "state", title: "Trạng thái đơn hàng", render: (value) => esc(value) },
        { data: "sku", title: "SKU", className: "text-nowrap", render: (value) => esc(value) },
        { data: "quantity", title: "Số lượng", className: "num", render: formatQty },
        { data: "amount_total", title: "Giá trị dòng hàng", className: "num", render: money },
        { data: "sales_channel", title: "Kênh bán", render: (value) => esc(value) },
        { data: "item_type_display", title: "Loại dòng hàng", render: (value) => esc(value) },
      ],
      autoWidth: false,
      scrollX: true,
      language: { ...APP.DATATABLE.LANGUAGE_VI, info: "Hiển thị _START_ - _END_ của _TOTAL_ đơn hàng" },
    });
  }
  function loadOrders() {
    ordersFilters = filters();
    if (ordersTable) ordersTable.ajax.reload();
    else buildOrdersTable();
  }
  function loadAll() {
    if (!validPeriod()) return;
    loader.next();
    loadKpi();
    loadDaily();
    loadBySale();
    loadTopCustomers();
    loadOrders();
  }
  function loadMeta() {
    begin();
    return Api.get(RPT.meta).done(applyMeta).fail(() => $("#dmUpdated").text("Không tải được")).always(end);
  }

  $(function () {
    if (typeof Loading !== "undefined") Loading.hide();
    $("#dmSearch, #dmRefresh").addClass("rpt-busy-btn");
    $(".rpt-card").has(".rpt-loading").addClass("is-loading");
    $("#dmOrdersTable").on("preXhr.dt", begin).on("xhr.dt", end);
    loadMeta().done(loadAll);
    $("#dmFilter").on("submit", (event) => {
      event.preventDefault();
      loadAll();
    });
    $("#dmPeriod").on("change", () => {
      toggleCustom();
      if ($("#dmPeriod").val() !== CUSTOM) loadAll();
    });
    $("#dmType, #dmState, #dmOrderType, #dmWarehouse").on("change", loadAll);
    let searchTimer = null;
    $("#dmOrdersSearch").on("input", function () {
      clearTimeout(searchTimer);
      const value = this.value.trim();
      searchTimer = setTimeout(() => ordersTable && ordersTable.search(value).draw(), 500);
    });
    $("#dmOrdersExport").on("click", function (event) {
      event.preventDefault();
      if ($(this).hasClass("disabled") || !ordersTable) return;
      Api.download(RPT.ordersExport, { ...ordersFilters, "search[value]": ordersTable.search() });
    });
    $("#dmRefresh").on("click", () => {
      $("#dmType, #dmState, #dmOrderType, #dmWarehouse").val("");
      $("#dmOrdersSearch").val("");
      if (ordersTable) ordersTable.search("");
      $("#dmPeriod").val(meta.months.length ? meta.months[0].value : CUSTOM);
      toggleCustom();
      pageCache.clear();
      loadAll();
    });
  });
})();
