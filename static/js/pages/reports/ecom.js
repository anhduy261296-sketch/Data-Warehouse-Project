/*
 * Báo cáo > E-commerce (templates/reports/ecom.html).
 * Moi vung goi 1 API rieng voi cung bo loc (date_from, date_to, channel, shop); server cache theo phien ban du lieu OMS.
 * Bang chi tiet: DataTables server-side co cache trang; bam SKU o bang Top 10 -> loc bang chi tiet theo SKU.
 */
(function () {
  const RPT = ENDPOINTS.reports.ecom;
  const esc = escapeHtml;
  // tien / so luong hien so nguyen (du lieu goc co so le do phan bo giam gia; file Excel giu nguyen)
  const money = (v) => formatAmount(v === null || v === undefined || v === "" ? v : Math.round(v));
  const BLUE_LIGHT = "rgba(59, 130, 246, 0.35)";
  const NAVY = "#1e3a8a";
  const CUSTOM = "custom";
  const STATUS_BADGE = {
    "Thêm mới": "badge-primary",
    "Đang xử lý": "badge-info",
    "Hoàn thành": "badge-success",
    Hủy: "badge-secondary",
    "Trả hàng": "badge-warning",
  };
  let meta = { months: [], channels: [], shops: [], max_range_days: 30 };
  let ordersTable = null;
  let skuFilter = "";

  // ---- bo loc ------------------------------------------------------------------------------------------
  function iso(d) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }
  function todayVn() {
    return new Date(new Date().toLocaleString("en-US", { timeZone: APP.TIMEZONE }));
  }
  function monthRange(value) {
    const [y, m] = value.split("-").map(Number);
    const last = new Date(y, m, 0);
    const today = todayVn();
    return { date_from: `${value}-01`, date_to: iso(last < today ? last : today) };
  }
  function period() {
    const p = $("#ecPeriod").val();
    if (p === CUSTOM) return { date_from: $("#ecFrom").val(), date_to: $("#ecTo").val() };
    return p ? monthRange(p) : {};
  }
  function filters() {
    return { ...period(), channel: $("#ecChannel").val(), shop: $("#ecShop").val() };
  }
  function validPeriod() {
    const { date_from: f, date_to: t } = period();
    let msg = "";
    if (!f || !t) msg = "Chọn đủ Từ ngày và Đến ngày.";
    else if (f > t) msg = "Từ ngày phải trước Đến ngày.";
    else if ((new Date(t) - new Date(f)) / 86400000 > meta.max_range_days)
      msg = `Khoảng ngày tối đa ${meta.max_range_days + 1} ngày. Xem dài hơn: chọn từng tháng.`;
    $("#ecFilterError").text(msg).toggleClass("d-none", !msg);
    return !msg;
  }

  function fillShops() {
    const channel = $("#ecChannel").val();
    const current = $("#ecShop").val();
    const channelName = Object.fromEntries(meta.channels.map((c) => [c.code, c.name]));
    const $shop = $("#ecShop").empty().append($("<option>").val("").text("Tất cả"));
    meta.shops
      .filter((s) => !channel || s.channel === channel)
      .forEach((s) =>
        $shop.append(
          $("<option>")
            .val(s.id)
            .text(channel ? s.name : `${s.name} (${channelName[s.channel] || s.channel})`),
        ),
      );
    $shop.val($shop.find(`option[value="${current}"]`).length ? current : "");
  }

  function applyMeta(m) {
    meta = m;
    const $p = $("#ecPeriod");
    const keep = $p.val();
    $p.empty();
    m.months.forEach((mo) =>
      $p.append(
        $("<option>")
          .val(mo.value)
          .text(`Tháng ${mo.value.slice(5)}/${mo.value.slice(0, 4)}`),
      ),
    );
    $p.append($("<option>").val(CUSTOM).text("Khoảng ngày tùy chọn..."));
    $p.val(keep && $p.find(`option[value="${keep}"]`).length ? keep : m.months.length ? m.months[0].value : CUSTOM);
    const $c = $("#ecChannel");
    const keepChannel = $c.val();
    $c.empty().append($("<option>").val("").text("Tất cả"));
    // nhom theo danh muc OMS: san online / kenh offline (kenh chua co don E-com van hien de chon)
    [
      ["online", "Sàn online"],
      ["offline", "Kênh offline"],
      ["", "Khác"],
    ].forEach(([op, label]) => {
      const items = m.channels.filter((c) => (c.operation || "") === op);
      if (!items.length) return;
      const $g = $("<optgroup>").attr("label", label);
      items.forEach((c) => $g.append($("<option>").val(c.code).text(c.name)));
      $c.append($g);
    });
    $c.val($c.find(`option[value="${keepChannel}"]`).length ? keepChannel : "");
    fillShops();
    $("#ecUpdated").text(formatUtcDateTime(m.updated_at));
    $("#ecChannelsRefresh").attr(
      "title",
      `Kéo lại danh mục kênh bán từ OMS. Lần cập nhật trước: ${formatUtcDateTime(m.channels_loaded_at)}`,
    );
    toggleCustom();
  }

  function toggleCustom() {
    const custom = $("#ecPeriod").val() === CUSTOM;
    $(".ec-custom").toggleClass("d-none", !custom);
    if (custom && !$("#ecFrom").val()) {
      const m = meta.months[0] ? monthRange(meta.months[0].value) : { date_from: iso(todayVn()), date_to: iso(todayVn()) };
      $("#ecFrom").val(m.date_from);
      $("#ecTo").val(m.date_to);
    }
  }

  // ---- khoa nut khi dang tai (core/report.js, dung chung voi trang Ton kho) ------------------------------
  const pageCache = Api.createPageCache();
  const SEARCH_HTML = '<i class="fas fa-search mr-1"></i> Xem báo cáo';
  function setBusy(on) {
    $("#ecSearch, #ecRefresh").prop("disabled", on);
    $("#ecOrdersExport")
      .toggleClass("disabled", on)
      .attr("aria-disabled", on ? "true" : null);
    $("#ecSearch").html(on ? '<span class="spinner-border spinner-border-sm mr-1"></span> Đang tải...' : SEARCH_HTML);
  }
  const loader = ReportLoader.create({ setBusy, lockAlways: true });
  const { begin, end } = loader;
  function area(ids, path, render) {
    return loader.area(ids, path, filters(), render);
  }

  function emptyHtml(cols) {
    return `<tr><td colspan="${cols}" class="text-center text-muted">${APP.MESSAGES.NO_DATA}</td></tr>`;
  }

  // ---- tung vung -----------------------------------------------------------------------------------------
  const KPI_CARDS = $(".ec-stat")
    .map((_, el) => `#${el.id}`)
    .get();
  function loadKpi() {
    return area(KPI_CARDS, RPT.kpi, (d) => {
      const set = (key, text) => $(`[data-kpi="${key}"]`).text(text);
      set("revenue_short", formatMoneyShort(d.revenue, 2));
      set("revenue", money(d.revenue));
      set("total_orders", money(d.total_orders));
      ["new", "processing", "success", "cancel", "return"].forEach((k) => {
        set(`${k}_orders`, money(d[`${k}_orders`]));
        set(`${k}_rate`, formatRate(d[`${k}_rate`]));
      });
      set("avg_order_value", formatMoneyShort(d.avg_order_value));
      set("avg_sku_per_order", formatQty(d.avg_sku_per_order));
      set("avg_qty_per_order", formatQty(d.avg_qty_per_order));
    });
  }

  function loadDaily() {
    return area(["#ecDaily"], RPT.daily, (d) => {
      const data = d.data;
      ChartKit.render("ecDailyChart", {
        data: {
          labels: data.map((r) => `${r.day.slice(8, 10)}/${r.day.slice(5, 7)}`),
          datasets: [
            {
              type: "line",
              label: "Số đơn hàng",
              data: data.map((r) => r.orders),
              yAxisID: "y1",
              borderColor: NAVY,
              backgroundColor: NAVY,
              pointRadius: 3,
              tension: 0.25,
              order: 0,
            },
            {
              type: "bar",
              label: "Doanh thu",
              data: data.map((r) => r.revenue),
              yAxisID: "y",
              backgroundColor: BLUE_LIGHT,
              borderRadius: 4,
              maxBarThickness: 26,
              order: 1,
            },
          ],
        },
        options: {
          maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          plugins: {
            legend: { position: "bottom", labels: { boxWidth: 12 } },
            tooltip: {
              callbacks: { label: (c) => (c.dataset.yAxisID === "y" ? `Doanh thu: ${money(c.raw)}` : `Số đơn: ${money(c.raw)}`) },
            },
          },
          scales: {
            y: {
              ticks: { callback: (v) => formatMoneyShort(v, 1) },
              grid: { color: APP.COLORS.CHART_GRID },
              title: { display: true, text: "Doanh thu" },
            },
            y1: { position: "right", grid: { display: false }, ticks: { precision: 0 }, title: { display: true, text: "Số đơn" } },
            x: { grid: { display: false }, ticks: { font: { size: 10 }, maxRotation: 0, autoSkip: true } },
          },
        },
      });
    });
  }

  /** Nhan truc x: tach thanh 2 dong dai gan bang nhau tai dau cach (vd "Tran Hoang / Lien Thao") de ten khong de nhau. */
  function wrapLabel(text) {
    const words = (text || "").split(" ");
    if (words.length < 2) return text;
    let best = [text];
    let bestLen = Infinity;
    for (let i = 1; i < words.length; i += 1) {
      const lines = [words.slice(0, i).join(" "), words.slice(i).join(" ")];
      const len = Math.max(lines[0].length, lines[1].length);
      if (len < bestLen) [best, bestLen] = [lines, len];
    }
    return best;
  }

  /** Bieu do cot dung, moi cot 1 mau pastel; format: nhan tren cot + truc; tooltip(i): [tieu de, dong 1, dong 2...] khi re chuot. */
  function vbar(id, labels, values, format, tooltip) {
    ChartKit.render(id, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            data: values,
            backgroundColor: labels.map((_, i) => APP.COLORS.PASTEL[i % APP.COLORS.PASTEL.length]),
            borderRadius: 6,
            maxBarThickness: 56,
          },
        ],
      },
      plugins: [ChartKit.valueLabels],
      options: {
        maintainAspectRatio: false,
        layout: { padding: { top: 18 } },
        plugins: {
          legend: { display: false },
          valueLabels: { format },
          tooltip: { callbacks: { title: (c) => tooltip(c[0].dataIndex)[0], label: (c) => tooltip(c.dataIndex).slice(1) } },
        },
        scales: {
          y: { beginAtZero: true, ticks: { callback: (v) => format(v) }, grid: { color: APP.COLORS.CHART_GRID } },
          x: {
            grid: { display: false },
            ticks: {
              font: { size: 11 },
              autoSkip: false,
              maxRotation: 0,
              callback(v) {
                return wrapLabel(this.getLabelForValue(v));
              },
            },
          },
        },
      },
    });
  }

  function loadBySale() {
    return area(["#ecSaleRevenue", "#ecSaleQty"], RPT.bySale, (d) => {
      const tip = (rows) => (i) => [rows[i].name, `Doanh thu: ${money(rows[i].revenue)} đ`, `Sản lượng: ${money(rows[i].qty)}`];
      const rows = d.data.filter((r) => r.revenue || r.qty);
      vbar(
        "ecSaleRevenueChart",
        rows.map((r) => r.name),
        rows.map((r) => r.revenue),
        (v) => formatMoneyShort(v, 1),
        tip(rows),
      );
      // San luong ban (so san pham, bo don huy, gom qua KM) - giong Control Tower
      const byQty = [...rows].sort((a, b) => b.qty - a.qty);
      vbar(
        "ecSaleQtyChart",
        byQty.map((r) => r.name),
        byQty.map((r) => r.qty),
        money,
        tip(byQty),
      );
    });
  }

  /** Dong bang Top 10; first = cot so dung truoc ("revenue" | "qty"), % theo cot do. Bam ma SKU -> loc bang chi tiet. */
  function topRows(rows, first) {
    const cols = first === "revenue" ? ["revenue", "qty"] : ["qty", "revenue"];
    return rows
      .map(
        (r, i) =>
          `<tr><td>${i + 1}</td><td class="text-nowrap"><a href="#" class="ec-sku-link" data-sku="${esc(r.sku)}" title="Xem chi tiết đơn của SKU này">${esc(r.sku)}</a></td>` +
          `<td class="rpt-name-fill" title="${esc(r.item_name)}">${esc(r.item_name)}</td>` +
          `<td class="num total">${money(r[cols[0]])}</td><td class="num">${money(r[cols[1]])}</td><td class="num">${formatRate(r[`${first}_share`])}</td></tr>`,
      )
      .join("");
  }
  function loadTopProducts() {
    return area(["#ecTopRevenue", "#ecTopQty"], RPT.topProducts, (d) => {
      $("#ecTopRevenue tbody").html(topRows(d.by_revenue, "revenue") || emptyHtml(6));
      $("#ecTopQty tbody").html(topRows(d.by_qty, "qty") || emptyHtml(6));
    });
  }

  // ---- bang chi tiet -------------------------------------------------------------------------------------
  let ordersFilters = {};
  function buildOrdersTable() {
    ordersTable = $("#ecOrdersTable").DataTable({
      serverSide: true,
      processing: true,
      searchDelay: 500,
      pageLength: APP.DATATABLE.PAGE_LENGTH,
      // o tim kiem dat cung hang voi bo loc tren tieu de card (#ecOrdersSearch) -> bo "f" mac dinh cua DataTables
      dom: "<'table-responsive'tr><'d-flex justify-content-between align-items-center flex-wrap mt-2'i<'d-flex align-items-center rpt-pager'lp>>",
      order: [[0, "desc"]],
      ajax: Api.dataTableSource(RPT.orders, () => ordersFilters, pageCache),
      columns: [
        {
          data: "created_at",
          title: "Ngày tạo",
          className: "text-nowrap",
          render: (v) => (v ? `${v.slice(8, 10)}/${v.slice(5, 7)}/${v.slice(0, 4)} ${v.slice(11, 16)}` : ""),
        },
        { data: "order_number", title: "Mã đơn", className: "text-nowrap", render: (v) => esc(v) },
        { data: "channel_name", title: "Sàn", render: (v) => esc(v) },
        { data: "shop_name", title: "Gian hàng", className: "text-nowrap", render: (v) => esc(v) },
        { data: "employee_name", title: "Sale", className: "text-nowrap", render: (v) => esc(v) },
        { data: "status", title: "Trạng thái OMS", render: (v) => esc(v) },
        {
          data: "status_group_label",
          title: "Nhóm TT",
          className: "text-nowrap",
          render: (v) => `<span class="badge ${STATUS_BADGE[v] || "badge-light"}">${esc(v)}</span>`,
        },
        { data: "line_type", title: "Dòng", render: (v) => (v === "Trả" ? `<span class="text-danger">${esc(v)}</span>` : esc(v)) },
        {
          data: "item_kind",
          title: "Loại",
          className: "text-nowrap",
          render: (v) => (v === "KM" ? `<span class="badge badge-light">KM</span>` : esc(v)),
        },
        { data: "sku", title: "SKU", className: "text-nowrap", render: (v) => esc(v) },
        {
          data: "item_name",
          title: "Tên sản phẩm",
          className: "rpt-name-cell",
          render: (v) => esc(v),
          createdCell: (td, v) => td.setAttribute("title", v || ""),
        },
        { data: "quantity", title: "SL", className: "num", render: money },
        { data: "price", title: "Giá niêm yết", className: "num", render: money },
        { data: "amount_before_vat", title: "Trước VAT", className: "num", render: money },
        { data: "amount", title: "Sau VAT", className: "num", render: money },
        { data: "net_amount", title: "Doanh thu tính BC", className: "num total", render: money },
      ],
      language: {
        ...APP.DATATABLE.LANGUAGE_VI,
        info: "Hiển thị _START_ - _END_ của _TOTAL_ dòng",
      },
    });
  }
  function loadOrders() {
    ordersFilters = { ...filters(), status_group: $("#ecStatusGroup").val(), sku: skuFilter };
    $("#ecSkuChip")
      .toggleClass("d-none", !skuFilter)
      .html(skuFilter ? `SKU: ${esc(skuFilter)} <a href="#" class="text-white ml-1" id="ecSkuClear" title="Bỏ lọc SKU">&times;</a>` : "");
    if (ordersTable) ordersTable.ajax.reload();
    else buildOrdersTable();
  }

  function filterSku(sku) {
    skuFilter = sku;
    loadOrders();
    document.getElementById("ecOrdersCard").scrollIntoView({ behavior: "smooth" });
  }

  function loadAll() {
    if (!validPeriod()) return;
    loader.next();
    loadKpi();
    loadDaily();
    loadBySale();
    loadTopProducts();
    loadOrders();
  }

  function loadMeta() {
    begin();
    return Api.get(RPT.meta)
      .done(applyMeta)
      .fail(() => $("#ecUpdated").text("Không tải được"))
      .always(end);
  }

  // ---- nut "Cap nhat kenh ban" (chi quan tri): kich hoat DAG chay tay tren Airflow roi cho ket qua --------
  const POLL_MS = 3000;
  const POLL_MAX = 60;
  function channelsMsg(text, kind) {
    $("#ecChannelsMsg").removeClass("d-none alert-info alert-success alert-danger").addClass(`alert alert-${kind}`).html(text);
  }
  function refreshChannels() {
    const $btn = $("#ecChannelsRefresh");
    const html = $btn.html();
    const done = () => $btn.prop("disabled", false).html(html);
    $btn.prop("disabled", true).html('<span class="spinner-border spinner-border-sm mr-1"></span> Đang cập nhật...');
    channelsMsg("Đang kéo danh mục kênh bán từ OMS...", "info");
    Api.post(RPT.channelsRefresh)
      .done((r) => {
        let tries = 0;
        const poll = () =>
          Api.get(RPT.channelsRefreshStatus, { run_id: r.run_id })
            .done((s) => {
              if (s.state === "success") {
                channelsMsg("Đã cập nhật danh mục kênh bán.", "success");
                done();
                pageCache.clear();
                loadMeta().done(loadAll);
              } else if (s.state === "failed") {
                channelsMsg("Cập nhật kênh bán thất bại - xem log DAG <b>oms_sales_channels_manual</b> trên Airflow.", "danger");
                done();
              } else if (++tries >= POLL_MAX) {
                channelsMsg("Chưa xong sau 3 phút - kiểm tra DAG <b>oms_sales_channels_manual</b> trên Airflow.", "danger");
                done();
              } else setTimeout(poll, POLL_MS);
            })
            .fail((x) => {
              channelsMsg(esc((x.responseJSON || {}).error || "Không kiểm tra được trạng thái."), "danger");
              done();
            });
        setTimeout(poll, POLL_MS);
      })
      .fail((x) => {
        channelsMsg(esc((x.responseJSON || {}).error || "Không gọi được máy chủ."), "danger");
        done();
      });
  }

  $(function () {
    if (typeof Loading !== "undefined") Loading.hide();
    $("#ecSearch, #ecRefresh").addClass("rpt-busy-btn");
    $(".rpt-card").has(".rpt-loading").addClass("is-loading");
    $("#ecOrdersTable").on("preXhr.dt", begin).on("xhr.dt", end);
    loadMeta().done(loadAll);

    $("#ecFilter").on("submit", (e) => {
      e.preventDefault();
      loadAll();
    });
    $("#ecPeriod").on("change", () => {
      toggleCustom();
      if ($("#ecPeriod").val() !== CUSTOM) loadAll();
    });
    $("#ecChannel").on("change", () => {
      fillShops();
      loadAll();
    });
    $("#ecShop").on("change", loadAll);
    $("#ecStatusGroup").on("change", loadOrders);
    let searchTimer = null;
    $("#ecOrdersSearch").on("input", function () {
      clearTimeout(searchTimer);
      const value = this.value.trim();
      searchTimer = setTimeout(() => ordersTable && ordersTable.search(value).draw(), 500);
    });

    $(document).on("click", ".ec-sku-link", function (e) {
      e.preventDefault();
      filterSku($(this).data("sku").toString());
    });
    $(document).on("click", "#ecSkuClear", (e) => {
      e.preventDefault();
      skuFilter = "";
      loadOrders();
    });
    $("#ecOrdersExport").on("click", function (e) {
      e.preventDefault();
      if ($(this).hasClass("disabled") || !ordersTable) return;
      Api.download(RPT.ordersExport, { ...ordersFilters, "search[value]": ordersTable.search() });
    });

    $("#ecRefresh").on("click", () => {
      $("#ecChannel, #ecShop, #ecStatusGroup").val("");
      $("#ecOrdersSearch").val("");
      if (ordersTable) ordersTable.search("");
      skuFilter = "";
      $("#ecPeriod").val(meta.months.length ? meta.months[0].value : CUSTOM);
      toggleCustom();
      fillShops();
      pageCache.clear();
      loadAll();
    });

    $("#ecChannelsRefresh").on("click", refreshChannels);
  });
})();
