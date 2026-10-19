(function () {
  const RPT = ENDPOINTS.reports.inventory;
  const fmt = formatQty;
  const esc = escapeHtml;
  const PALETTE = APP.COLORS.PALETTE;
  let meta = { warehouses: [], groups: [], statuses: [] };
  const whsColor = {};
  const whsName = {};
  let skuTable = null;

  function filters() {
    return { q: $("#rptQ").val().trim(), group: $("#rptGroup").val(), whs: $("#rptWhs").val(), status: $("#rptStatus").val() };
  }

  const pageCache = Api.createPageCache();
  let skuFilters = {};
  const SEARCH_HTML = '<i class="fas fa-search mr-1"></i> Tìm kiếm';
  function setBusy(on) {
    $("#rptSearch, #rptRefresh").prop("disabled", on);
    $("#rptExport, #rptLocExport")
      .toggleClass("disabled", on)
      .attr("aria-disabled", on ? "true" : null);
    $("#rptSearch").html(on ? '<span class="spinner-border spinner-border-sm mr-1"></span> Đang tải...' : SEARCH_HTML);
  }

  const loader = ReportLoader.create({ setBusy, lockAlways: false });
  const { lock, begin, end } = loader;
  function area(id, path, render) {
    return loader.area(id, path, filters(), render);
  }

  function loadKpi() {
    ["#rptKpiSku", "#rptKpiWhs", "#rptKpiQty"].forEach((id) => $(id).addClass("is-loading"));
    const g = loader.current();
    begin();
    return Api.get(RPT.kpi, filters())
      .always(end)
      .done((d) => {
        if (g === loader.current())
          $("[data-kpi]").each(function () {
            $(this).text(fmt(d[$(this).data("kpi")]));
          });
      })
      .fail(() => $("[data-kpi]").text("!"))
      .always(() => ["#rptKpiSku", "#rptKpiWhs", "#rptKpiQty"].forEach((id) => $(id).removeClass("is-loading")));
  }

  function whsCell(byWhs, total) {
    const list = Object.entries(byWhs || {}).sort((a, b) => b[1] - a[1]);
    if (!list.length) return "";
    const [code, qty] = list[0];
    const rest = list.slice(1);
    const more = rest.length
      ? `<span class="rpt-whs-more" title="${esc(rest.map(([c, q]) => `${c}: ${fmt(q)}`).join(", "))}">+${rest.length} kho</span>`
      : "";
    return (
      `<div class="rpt-whs-cell"><span class="rpt-whs-main" title="${esc(code)} - ${esc(whsName[code] || "")}">` +
      `<i style="background:${whsColor[code] || APP.COLORS.NEUTRAL_LIGHT}"></i>${esc(code)} <b>${fmt(qty)}</b>` +
      ` <small>${formatRate(total ? qty / total : 0, 0)}</small></span>${more}</div>`
    );
  }

  function loadTopSku() {
    return area("#rptTopSku", RPT.topSku, (d) => {
      const rows = d.data
        .map(
          (r, i) =>
            `<tr><td>${i + 1}</td><td class="text-nowrap">${esc(r.sku)}</td><td class="rpt-name-fill" title="${esc(r.item_name)}">${esc(r.item_name)}</td>` +
            `<td>${esc(r.uom)}</td><td class="num total">${fmt(r.total_qty)}</td><td>${whsCell(r.by_warehouse, r.total_qty)}</td></tr>`,
        )
        .join("");
      $("#rptTopSku tbody").html(rows || `<tr><td colspan="6" class="text-center text-muted">${APP.MESSAGES.NO_DATA}</td></tr>`);
    });
  }

  function loadByWarehouse() {
    $("#rptTopWhs").addClass("is-loading");
    return area("#rptByWhs", RPT.byWarehouse, (d) => {
      const data = d.data;
      const total = data.reduce((sum, r) => sum + (r.total_qty || 0), 0);
      ChartKit.hbar("rptWhsChart", {
        labels: data.map((r) => r.code),
        values: data.map((r) => r.total_qty),
        colors: data.map((r) => whsColor[r.code] || APP.COLORS.NEUTRAL),
        label: (v) => fmt(v),
        tick: (v) => fmt(v),
        tooltip: (i) => [
          `${data[i].code} - ${data[i].name}`,
          `Tồn: ${fmt(data[i].total_qty)} (${formatRate(total ? data[i].total_qty / total : 0)})`,
          `Số SKU: ${fmt(data[i].sku_count)}`,
        ],
      });
      const max = Math.max(1, ...data.map((r) => r.total_qty || 0));
      const rows = data
        .slice(0, 10)
        .map(
          (r, i) =>
            `<tr><td>${i + 1}</td><td><b>${esc(r.code)}</b><div class="small text-muted rpt-name rpt-name--whs" title="${esc(r.name)}">${esc(r.name)}</div></td>` +
            `<td class="num">${fmt(r.total_qty)}</td><td><div class="rpt-bar"><span style="width:${(r.total_qty / max) * 100}%;background:${whsColor[r.code] || APP.COLORS.NEUTRAL}"></span></div></td><td class="num">${fmt(r.sku_count)}</td></tr>`,
        )
        .join("");
      $("#rptTopWhs tbody").html(rows || `<tr><td colspan="5" class="text-center text-muted">${APP.MESSAGES.NO_DATA}</td></tr>`);
    }).always(() => $("#rptTopWhs").removeClass("is-loading"));
  }

  function loadByGroup() {
    return area("#rptByGroup", RPT.byGroup, (d) => {
      const data = d.data;
      const total = data.reduce((sum, r) => sum + (r.total_qty || 0), 0);
      const colors = data.map((_, i) => PALETTE[i % PALETTE.length]);
      ChartKit.render("rptGroupChart", {
        type: "doughnut",
        data: {
          labels: data.map((r) => r.name),
          datasets: [{ data: data.map((r) => r.total_qty), backgroundColor: colors, borderWidth: 2, borderColor: "#fff" }],
        },
        options: {
          cutout: "62%",
          maintainAspectRatio: false,
          plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${c.label}: ${fmt(c.raw)}` } } },
        },
      });
      $("#rptGroupTotal").text(fmt(total));
      $("#rptByGroup .rpt-legend tbody").html(
        data
          .map(
            (r, i) =>
              `<tr><td title="${esc(r.name)}"><span class="rpt-dot" style="background:${colors[i]}"></span>${esc(r.name)}</td>` +
              `<td class="text-right text-muted">${formatRate(total ? r.total_qty / total : 0)}</td><td class="text-right"><b>${fmt(r.total_qty)}</b></td></tr>`,
          )
          .join(""),
      );
    });
  }

  function buildSkuTable() {
    const whsCols = meta.warehouses.map((w) => ({
      data: w.code,
      title: w.code,
      className: "num",
      orderable: false,
      defaultContent: "",
      render: (v) => (v ? fmt(v) : ""),
    }));
    const columns = [
      { data: "sku", title: "SKU", className: "text-nowrap" },
      {
        data: "item_name",
        title: "Tên sản phẩm",
        className: "rpt-name-cell",
        render: (v) => esc(v),
        createdCell: (td, v) => td.setAttribute("title", v || ""),
      },
      { data: "uom", title: "ĐVT", orderable: false },
      { data: "total_qty", title: "Tổng tồn", className: "num total", render: fmt },
      { data: "available_qty", title: "Khả dụng", className: "num", render: fmt },
      { data: "held_qty", title: "Đang giữ", className: "num", render: fmt },
      ...whsCols,
    ];
    skuTable = $("#rptSkuTable").DataTable({
      serverSide: true,
      processing: true,
      searching: false,
      pageLength: APP.DATATABLE.PAGE_LENGTH,
      dom: "<'table-responsive'tr><'d-flex justify-content-between align-items-center flex-wrap mt-2'i<'d-flex align-items-center rpt-pager'lp>>",
      order: [[3, "desc"]],
      ajax: Api.dataTableSource(RPT.bySku, () => skuFilters, pageCache),
      columns,
      initComplete: function () {
        this.api()
          .columns()
          .every(function (i) {
            const w = meta.warehouses[i - 6];
            if (w)
              $(this.header()).attr("title", `${w.code} - ${w.name}`).tooltip({ container: "body", placement: "top", trigger: "hover" });
          });
      },
      language: { ...APP.DATATABLE.LANGUAGE_VI, info: "Hiển thị _START_ - _END_ của _TOTAL_ SKU" },
    });
  }

  let locTable = null;
  let locFilters = null;
  function buildLocTable() {
    locTable = $("#rptLocTable").DataTable({
      serverSide: true,
      processing: true,
      searching: false,
      pageLength: APP.DATATABLE.PAGE_LENGTH,
      dom: "<'table-responsive'tr><'d-flex justify-content-between align-items-center flex-wrap mt-2'i<'d-flex align-items-center rpt-pager'lp>>",
      order: [[0, "asc"]],
      ajax: Api.dataTableSource(RPT.byLocation, () => locFilters, pageCache),
      columns: [
        { data: "sku", title: "Mã hàng", className: "text-nowrap" },
        {
          data: "item_name",
          title: "Tên hàng",
          className: "rpt-name-cell",
          render: (v) => esc(v),
          createdCell: (td, v) => td.setAttribute("title", v || ""),
        },
        { data: "whs", title: "Kho", className: "text-nowrap" },
        { data: "whs_name", title: "Tên kho", orderable: false, render: (v) => esc(v) },
        { data: "status", title: "Trạng thái", className: "text-nowrap", render: (v) => esc(v) },
        { data: "qty", title: "WMS", className: "num total", render: fmt },
        { data: "uom", title: "ĐVT", orderable: false, render: (v) => esc(v) },
      ],
      language: { ...APP.DATATABLE.LANGUAGE_VI, info: "Hiển thị _START_ - _END_ của _TOTAL_ dòng" },
    });
  }

  function hasFilter() {
    return Object.values(filters()).some((v) => v);
  }

  function resetLoc() {
    $("#rptLocExport").addClass("d-none");
    $("#rptLocWrap").addClass("d-none");
    $("#rptLocHint").removeClass("d-none");
  }
  function loadAll(fromSearch) {
    loader.next();
    loadKpi();
    loadTopSku();
    loadByWarehouse();
    loadByGroup();
    skuFilters = filters();
    if (skuTable) skuTable.ajax.reload();
    else buildSkuTable();
    if (fromSearch === true && hasFilter()) {
      $("#rptLocHint").addClass("d-none");
      $("#rptLocWrap, #rptLocExport").removeClass("d-none");
      locFilters = filters();
      if (locTable) locTable.ajax.reload();
      else buildLocTable();
    } else if (fromSearch === true || fromSearch === "reset" || !hasFilter()) {
      resetLoc();
    }
    $("#rptExport").attr("href", Api.url(RPT.export, filters()));
  }

  $(function () {
    if (typeof Loading !== "undefined") Loading.hide();
    $("#rptSearch, #rptRefresh, #rptExport").addClass("rpt-busy-btn");
    $("#rptExport").on("click", function (e) {
      if ($(this).hasClass("disabled") || $(this).attr("href") === "#") e.preventDefault();
    });
    $(".rpt-card").has(".rpt-loading").addClass("is-loading");
    begin();
    Api.get(RPT.meta)
      .done((m) => {
        meta = m;
        m.warehouses.forEach((w, i) => {
          whsColor[w.code] = PALETTE[i % PALETTE.length];
          whsName[w.code] = w.name;
        });
        m.groups.forEach((g) => $("#rptGroup").append($("<option>").val(g.code).text(g.name)));
        m.warehouses.forEach((w) => $("#rptWhs").append($("<option>").val(w.code).text(`${w.code} - ${w.name}`)));
        m.statuses.forEach((s) => $("#rptStatus").append($("<option>").val(s).text(s)));
        $("#rptSnapshot").text(formatUtcDateTime(m.snapshot_at));
        $("#rptSkuTable, #rptLocTable").on("preXhr.dt", begin).on("xhr.dt", end);
        loadAll();
      })
      .fail(() => {
        $("#rptSnapshot").text("Không tải được");
        $(".rpt-card.is-loading").removeClass("is-loading");
      })
      .always(() => {
        end();
        $(".rpt-boot").removeClass("is-loading rpt-boot");
      });

    $("#rptLocExport").on("click", function (e) {
      e.preventDefault();
      if ($(this).hasClass("disabled") || !locTable) return;
      const [col, dir] = locTable.order()[0] || [0, "asc"];
      Api.download(RPT.byLocationExport, { ...(locFilters || {}), sort: locTable.settings().init().columns[col].data, dir });
    });
    $("#rptFilter").on("submit", (e) => {
      e.preventDefault();
      lock();
      loadAll(true);
    });

    $("#rptGroup, #rptWhs, #rptStatus").on("change", () => loadAll(true));

    $("#rptRefresh").on("click", () => {
      $("#rptQ").val("");
      $("#rptGroup, #rptWhs, #rptStatus").val("");
      pageCache.clear();
      lock();
      loadAll("reset");
    });
  });
})();
