(function () {
  const EP = ENDPOINTS.messaging;
  const FILE_PLACEHOLDER = "Chọn file Excel (.xlsx)";
  const PREVIEW_LIMIT = 10;
  const state = {
    upload: null,
    templates: [],
    template: null,
    mapping: null,
    fixed: {},
    result: null,
    valid: [],
    filtered: [],
    index: 0,
    seq: 0,
  };

  function setStep(step) {
    // step 3 = đã có khách hợp lệ để xác nhận -> bước 2 hoàn tất.
    $("#znsSteps li").each(function () {
      const n = Number($(this).data("step"));
      $(this)
        .toggleClass("is-active", n === Math.min(step, 2))
        .toggleClass("is-done", n < Math.min(step, 2));
    });
    $("#znsStep2").toggleClass("zns-locked", step < 2);
  }

  function cellText(value) {
    return value === null || value === undefined ? "" : escapeHtml(value);
  }

  function renderUpload(up) {
    $("#znsUploadCount").text(formatAmount(up.total_rows));
    $("#znsUploadResult").removeClass("d-none");
  }

  function upload(e) {
    e.preventDefault();
    const file = $("#znsFile")[0].files[0];
    if (!file) {
      Toast.warning("Vui lòng chọn file Excel.");
      return;
    }
    const form = new FormData();
    form.append("file", file);
    Loading.wrap(Api.upload(EP.upload, form), "Đang đọc file Excel...")
      .then((up) => {
        state.upload = up;
        state.mapping = null;
        state.fixed = {};
        renderUpload(up);
        setStep(2);
        return loadTemplates().then(() => (autoSelectTemplate(up.template_code) ? selectTemplate() : state.template && evaluate()));
      })
      .catch((x) => {
        Toast.error(Api.errorMessage(x, "Không đọc được file."), { title: "Upload thất bại" });
        $("#znsUploadResult").addClass("d-none");
      });
  }

  function autoSelectTemplate(code) {
    const match = code && state.templates.find((t) => String(t.zns_code) === String(code));
    if (!match || state.template === match.id) return false;
    $("#znsOwnerSelect").val("");
    renderTemplateOptions();
    $("#znsTemplateSelect").val(String(match.id));
    Toast.info(`Đã tự chọn mẫu <b>${escapeHtml(match.name)}</b> theo templatecode <code>${escapeHtml(code)}</code> trong file.`, {
      html: true,
    });
    return true;
  }

  function loadTemplates(force) {
    if (state.templates.length && !force) return $.Deferred().resolve().promise();
    return Api.get(EP.templates, { active: 1 }).done((res) => {
      state.templates = res.data || [];
      renderTemplateOptions();
    });
  }

  function renderTemplateOptions() {
    const owner = $("#znsOwnerSelect").val();
    const current = $("#znsTemplateSelect").val();
    const list = state.templates.filter((t) => !owner || t.owner === owner);
    $("#znsTemplateSelect").html(
      `<option value="">${list.length ? "Chọn mẫu tin..." : "Không có mẫu tin đang hoạt động"}</option>` +
        list
          .map(
            (t) =>
              `<option value="${t.id}"${String(t.id) === current ? " selected" : ""}>[${escapeHtml(t.owner)}] ${escapeHtml(t.name)} · ${escapeHtml(t.zns_code)}</option>`,
          )
          .join(""),
    );
  }

  function selectTemplate() {
    const id = Number($("#znsTemplateSelect").val()) || null;
    state.template = id;
    state.mapping = null;
    state.fixed = {};
    if (!id) {
      $("#znsConfig").addClass("d-none");
      $("#znsEvalSummary").empty();
      state.result = null;
      renderPreview();
      setStep(2);
      return;
    }
    evaluate();
  }

  function evaluate() {
    if (!state.upload || !state.template) return;
    const seq = ++state.seq;
    $("#znsStep2").addClass("is-busy");
    Api.postJson(EP.evaluate, { batch_id: state.upload.batch_id, template_id: state.template, mapping: state.mapping, fixed: state.fixed })
      .done((res) => {
        if (seq !== state.seq) return;
        state.result = res;
        state.mapping = res.mapping;
        renderConfig(res);
        renderPreview();
      })
      .fail((x) => {
        if (seq !== state.seq) return;
        ZnsUi.alertBox($("#znsEvalErrors"), escapeHtml(Api.errorMessage(x, "Không kiểm tra được dữ liệu.")));
        $("#znsConfig").removeClass("d-none");
      })
      .always(() => seq === state.seq && $("#znsStep2").removeClass("is-busy"));
  }

  function columnSelect(key, selected, columns) {
    return `<select class="form-control form-control-sm zns-map-select" data-key="${escapeHtml(key)}">
      <option value="">— Không dùng —</option>
      ${columns.map((c, i) => `<option value="${i}"${i === selected ? " selected" : ""}>${escapeHtml(c)}</option>`).join("")}</select>`;
  }

  function renderConfig(res) {
    const vars = res.template.variables;
    const customer = vars.filter((v) => v.source === "customer");
    const fixed = vars.filter((v) => v.source === "fixed");
    const label = (v, text) =>
      `<td>${escapeHtml(text || v.label || v.name)}${v.is_required ? '<span class="text-danger"> *</span>' : ""}</td>
       <td>${v.name ? `<span class="zns-var-tag">${escapeHtml(v.name)}</span>` : '<span class="text-muted">—</span>'}</td>`;
    const group = (kind, icon, title, valueTitle) =>
      `<tr class="zns-vars-group zns-vars-group--${kind}"><th><i class="fas ${icon} mr-1"></i>${title}</th><th>Mã biến</th><th>${valueTitle}</th></tr>`;
    const fixedValue = (v) => {
      const error = res.fixed_errors[v.name];
      if (error)
        return `<td class="zns-vars-value is-missing"><i class="fas fa-exclamation-circle mr-1"></i>${escapeHtml(error === "Bắt buộc nhập" ? "Chưa có dữ liệu" : error)}</td>`;
      const value = (res.fixed[v.name] || {}).display;
      return `<td class="zns-vars-value">${value ? escapeHtml(value) : '<span class="text-muted">—</span>'}</td>`;
    };
    $("#znsMapping").html(
      group("customer", "fa-user", "Theo khách hàng", "Cột trong file") +
        `<tr>${label({ is_required: true }, "Số điện thoại")}<td>${columnSelect("__phone__", res.mapping.__phone__, res.columns)}</td></tr>` +
        customer.map((v) => `<tr>${label(v)}<td>${columnSelect(v.name, res.mapping[v.name], res.columns)}</td></tr>`).join("") +
        (fixed.length
          ? group("fixed", "fa-lock", "Cố định · dùng chung", "Giá trị") + fixed.map((v) => `<tr>${label(v)}${fixedValue(v)}</tr>`).join("")
          : ""),
    );
    const editUrl = String($("#znsStep2").data("editUrl")).replace(/0\/$/, `${res.template.id}/`);
    $("#znsEditTemplate").attr("href", editUrl);
    const s = res.summary;
    const stat = (cls, text, value) => `<div class="zns-stat ${cls}"><span>${text}</span><b>${formatAmount(value)}</b></div>`;
    $("#znsEvalSummary").html(
      stat("", "Tổng", s.total) +
        stat("is-ok", "Hợp lệ", s.valid) +
        (s.invalid
          ? `<button type="button" class="zns-stat is-bad" id="znsShowInvalid" title="Xem các dòng lỗi"><span>Lỗi <i class="fas fa-eye ml-1"></i></span><b>${formatAmount(s.invalid)}</b></button>`
          : stat("", "Lỗi", 0)),
    );
    const errors = res.mapping_errors.concat(
      Object.keys(res.fixed_errors).length
        ? ['Mẫu tin còn thiếu / sai dữ liệu biến cố định - bấm "Sửa ở mẫu tin" để cập nhật rồi chọn lại mẫu.']
        : [],
    );
    ZnsUi.alertBox($("#znsEvalErrors"), errors.map(escapeHtml).join("<br>"));
    ZnsUi.alertBox($("#znsEvalWarnings"), (res.warnings || []).map(escapeHtml).join("<br>"), "warning");
    const invalid = res.rows.filter((r) => r.errors.length);
    $("#znsInvalidRows").html(
      invalid
        .slice(0, 500)
        .map(
          (r) =>
            `<tr><td class="num">${r.row_no}</td><td>${cellText(r.phone || r.raw_phone)}</td><td>${cellText(r.customer)}</td><td>${escapeHtml(r.errors.join("; "))}</td></tr>`,
        )
        .join(""),
    );
    $("#znsConfig").removeClass("d-none");
  }

  function canConfirm() {
    const r = state.result;
    return Boolean(r && r.summary.valid && !r.mapping_errors.length && !Object.keys(r.fixed_errors).length);
  }

  function renderPreview() {
    const r = state.result;
    state.valid = r ? r.rows.filter((x) => x.valid) : [];
    filterCustomers();
    setStep(state.valid.length ? 3 : 2);
    $("#znsConfirmBtn").prop("disabled", !canConfirm());
  }

  // Xem trước chỉ cần vài khách: dropdown hiện tối đa PREVIEW_LIMIT, ô tìm kiếm vẫn tìm trên toàn bộ khách hợp lệ.
  function filterCustomers() {
    const q = normalizeSearchText($("#znsCustomerSearch").val());
    const matches = state.valid.filter((x) => !q || normalizeSearchText(`${x.customer || ""} ${x.phone}`).includes(q));
    state.filtered = matches.slice(0, PREVIEW_LIMIT);
    state.index = 0;
    const more = matches.length - state.filtered.length;
    $("#znsCustomer").html(
      state.filtered.length
        ? state.filtered
            .map(
              (x, i) =>
                `<option value="${i}">Dòng ${x.row_no} · ${escapeHtml(x.customer || "(không tên)")} · ${escapeHtml(x.phone)}</option>`,
            )
            .join("") + (more > 0 ? `<option value="" disabled>… còn ${formatAmount(more)} khách, gõ tên / SĐT để tìm</option>` : "")
        : `<option value="">${q ? "Không tìm thấy khách hàng" : "Không có khách hàng hợp lệ"}</option>`,
    );
    showCustomer();
  }

  function showCustomer() {
    const x = state.filtered[state.index];
    $("#znsCustomer").val(x ? String(state.index) : "");
    $("#znsPrev").prop("disabled", state.index <= 0);
    $("#znsNext").prop("disabled", state.index >= state.filtered.length - 1);
    if (!x) {
      $("#znsCustomerMeta").empty();
      $("#znsMessagePreview").html(
        `<span class="text-muted">${state.result ? "Không có khách hàng hợp lệ để xem trước" : "Chọn mẫu tin"}</span>`,
      );
      return;
    }
    $("#znsCustomerMeta").text(`Dòng ${x.row_no} · SĐT Zalo ${x.phone}`);
    $("#znsMessagePreview").html(escapeHtml(x.content).replace(/\n/g, "<br>"));
  }

  function openConfirm() {
    const r = state.result;
    if (!canConfirm()) return;
    const t = r.template;
    const live = state.sendMode === "live";
    Dialog.confirm({
      title: "Gửi lô này để duyệt?",
      html: true,
      message: `<div class="mb-1">Mẫu: <b>${escapeHtml(t.name)}</b> · ${ZnsUi.codeChip(t.zns_code)} ${ZnsUi.ownerBadge(t.owner)}</div>
        <div class="mb-1">File: ${escapeHtml(state.upload.file_name)}</div>
        <div>Sẽ gửi: <b>${formatAmount(r.summary.valid)}</b> khách hàng${r.summary.invalid ? ` · <span class="text-danger">bỏ qua <b>${formatAmount(r.summary.invalid)}</b> dòng lỗi</span>` : ""}</div>
        <div class="small text-muted mt-2">Lô chuyển sang <b>Chờ duyệt</b>. Tin chỉ được gửi sau khi người khác duyệt.${live ? "" : " Server đang ở chế độ <b>chạy thử</b>: không có tin nào được gửi."}</div>`,
      confirmText: "Gửi duyệt",
      cancelText: "Quay lại",
      variant: "primary",
      icon: "fa-paper-plane",
    }).then((ok) => ok && submitConfirm());
  }

  function submitConfirm() {
    if (!state.upload || !canConfirm()) return;
    Loading.wrap(
      Api.postJson(EP.confirm, {
        batch_id: state.upload.batch_id,
        template_id: state.template,
        mapping: state.mapping,
        fixed: state.fixed,
      }),
      "Đang tạo lô gửi...",
    )
      .then((res) => {
        const msg = `Lô #${res.batch_id} gồm ${formatAmount(res.valid)} khách hàng đang chờ duyệt${res.invalid ? `, bỏ qua ${formatAmount(res.invalid)} dòng lỗi` : ""}.`;
        reset();
        Toast.success(msg, { title: "Đã gửi duyệt" });
        reloadHistory(true);
      })
      .catch((x) => Toast.error(Api.errorMessage(x, "Không xác nhận được lô gửi.")));
  }

  function reset() {
    Object.assign(state, { upload: null, template: null, mapping: null, fixed: {}, result: null, valid: [], filtered: [], index: 0 });
    state.seq += 1;
    $("#znsUploadForm")[0].reset();
    $("#znsFileName").text(FILE_PLACEHOLDER).removeClass("has-file");
    $("#znsUploadResult, #znsConfig").addClass("d-none");
    $("#znsEvalSummary").empty();
    $("#znsTemplateSelect").val("");
    $("#znsMapping").empty();
    $("#znsCustomerSearch").val("");
    renderPreview();
    setStep(1);
  }

  // Bảng phân trang phía server, cùng cấu hình bảng chi tiết ở báo cáo.
  const pagedTable = (scrollClass) => ({
    serverSide: true,
    processing: true,
    ordering: false,
    autoWidth: false,
    pageLength: APP.DATATABLE.PAGE_LENGTH,
    lengthMenu: APP.DATATABLE.LENGTH_MENU,
    dom: `<'table-responsive ${scrollClass}'tr><'d-flex justify-content-between align-items-center flex-wrap mt-2'i<'d-flex align-items-center rpt-pager'lp>>`,
    language: { ...APP.DATATABLE.LANGUAGE_VI, info: "Hiển thị _START_ - _END_ của _TOTAL_ dòng" },
    createdRow: (row, data) => {
      row.dataset.id = data.id;
    },
  });

  const canExportBatch = $("#znsHistoryCard").data("canExport") === 1;
  const HISTORY_COLUMNS = [
    {
      data: "id",
      className: "zns-actions",
      render: (id, type, b) => `
            <button type="button" class="btn btn-sm btn-light zns-batch-view" title="Xem chi tiết"><i class="far fa-eye"></i></button>
            ${canExportBatch ? `<a class="btn btn-sm btn-light" href="${Api.url(EP.batchExport(id))}" title="Xuất Excel"><i class="fas fa-file-excel text-success"></i></a>` : ""}
            ${
              b.can_cancel
                ? '<button type="button" class="btn btn-sm btn-light zns-batch-cancel" title="Dừng / hủy các khách chưa gửi"><i class="fas fa-ban text-danger"></i></button>'
                : ""
            }`,
    },
    {
      data: "id",
      render: (id, type, b) => `#${id}${b.parent_batch_id ? `<div class="small text-muted">Ref #${b.parent_batch_id}</div>` : ""}`,
    },
    { data: "confirmed_at", className: "zns-date-cell", render: (v) => formatUtcDateTime(v) },
    { data: "template_name", render: (v, type, b) => `${escapeHtml(v || "—")}<div class="mt-1">${ZnsUi.codeChip(b.zns_code)}</div>` },
    { data: "owner", render: (v) => ZnsUi.ownerBadge(v) },
    { data: "file_name", className: "zns-file-cell", render: (v) => escapeHtml(v) },
    { data: "total_rows", className: "num", render: (v) => formatAmount(v) },
    { data: "valid_rows", className: "num", render: (v) => formatAmount(v) },
    { data: "invalid_rows", className: "num", render: (v) => formatAmount(v) },
    { data: "status", render: (v, type, b) => ZnsUi.statusBadge(v, b.status_label) },
    { data: "sent_rows", className: "num", render: (v) => formatAmount(v) },
    { data: "failed_rows", className: "num", render: (v) => (v ? `<span class="text-danger">${formatAmount(v)}</span>` : "0") },
    { data: "unknown_rows", className: "num", render: (v) => (v ? `<span class="zns-text-warn">${formatAmount(v)}</span>` : "0") },
    { data: "created_by", render: (v) => ZnsUi.userChip(v) },
  ];

  // Cùng các lô như đang hiển thị thì chỉ cập nhật ô có thay đổi, để bảng không bị vẽ lại.
  function patchHistoryRows(list) {
    const shownRows = $("#znsHistoryRows")[0].rows;
    if (list.length !== shownRows.length || !list.every((b, i) => shownRows[i].dataset.id === String(b.id))) return false;
    const scratch = document.createElement("td");
    list.forEach((b, i) => {
      HISTORY_COLUMNS.forEach((column, j) => {
        scratch.innerHTML = column.render(b[column.data], "display", b);
        const shown = shownRows[i].cells[j];
        if (shown.innerHTML !== scratch.innerHTML) shown.innerHTML = scratch.innerHTML;
      });
    });
    return true;
  }

  // Lô đang gửi chạy ở server: tự làm mới ngầm (không qua lớp "Đang tải" của bảng) tới khi xong.
  const HISTORY_POLL_MS = 3000;
  let historyTimer = null;
  const nextPoll = () => {
    clearTimeout(historyTimer);
    historyTimer = setTimeout(pollHistory, HISTORY_POLL_MS);
  };
  function pollIfSending(list) {
    clearTimeout(historyTimer);
    if (list.some((b) => b.status === "sending")) nextPoll();
  }
  function pollHistory() {
    const params = historyTable.ajax.params();
    Api.get(EP.batches, params)
      .done((res) => {
        if (params !== historyTable.ajax.params()) return; // người dùng vừa đổi trang
        if (patchHistoryRows(res.data)) pollIfSending(res.data);
        else historyTable.ajax.reload(null, false);
      })
      .fail(nextPoll); // lỗi mạng thoáng qua: giữ nguyên bảng và thử lại ở nhịp sau
  }

  const historyTable = $("#znsHistoryTable")
    .on("xhr.dt", (e, settings, res) => {
      if (!res || !res.send_mode) return;
      state.sendMode = res.send_mode;
      // TODO: nhãn kiểm tra khi dev, xóa trước khi lên prod (cùng #znsSendMode và .zns-mode).
      $("#znsSendMode")
        .removeClass("d-none")
        .toggleClass("is-live", res.send_mode === "live")
        .text(res.send_mode === "live" ? "Gửi thật" : "Chạy thử · không gửi tin thật");
      pollIfSending(res.data);
    })
    .DataTable({ ...pagedTable(""), ajax: Api.dataTableSource(EP.batches), columns: HISTORY_COLUMNS });

  function reloadHistory(resetPaging = false) {
    historyTable.ajax.reload(null, resetPaging);
  }

  let currentBatchId = null;
  const batchTable = $("#znsBatchTable").DataTable({
    ...pagedTable("zns-scroll"),
    deferLoading: 0,
    ajax: (d, callback) =>
      Api.dataTableSource(EP.batchRecipients(currentBatchId), () => ({ status: $("#znsBatchFilter").val() }))(d, callback),
    columns: [
      {
        data: "id",
        orderable: false,
        render: (id, type, r) =>
          ["failed", "unknown"].includes(r.status) && !r.retried_in
            ? '<button type="button" class="btn btn-sm btn-light zns-skip-btn" title="Bỏ qua khách này, không gửi lại"><i class="fas fa-user-slash"></i></button>'
            : "",
      },
      { data: "row_no", className: "zns-row-no" },
      { data: "customer", render: (v) => cellText(v) },
      { data: "phone", render: (v) => cellText(v) },
      { data: "status", render: (v, type, r) => ZnsUi.statusBadge(v, r.status_label) },
      {
        data: "attempt_count",
        render: (v) =>
          v ? `<button type="button" class="btn btn-sm btn-light zns-attempts-btn" title="Xem từng lần gọi API">${v}</button>` : "—",
      },
      {
        data: "error",
        className: "zns-msg-cell",
        render: (error, type, r) =>
          `${
            r.status === "skipped"
              ? `<span class="text-muted">${r.error_kind_label ? `${escapeHtml(r.error_kind_label)}: ` : ""}${escapeHtml(error || "")}</span><div class="zns-skip-note"><i class="fas fa-user-slash mr-1"></i>Bỏ qua: ${escapeHtml(r.skip_reason || "")}${r.skipped_by ? ` · ${escapeHtml(r.skipped_by)}` : ""}</div>`
              : error
                ? `<span class="${r.status === "unknown" ? "zns-text-warn" : "text-danger"}">${r.error_kind_label ? `${escapeHtml(r.error_kind_label)}: ` : ""}${escapeHtml(error)}</span>`
                : escapeHtml(r.content || "")
          }${r.retried_in ? `<div class="small text-muted">Đã gửi lại ở lô #${r.retried_in}</div>` : ""}`,
      },
    ],
  });

  let batchErrors = [];
  function hideReasons() {
    $("#znsBatchReasons").addClass("d-none");
    $("#znsBatchStats .zns-stat-btn").attr("aria-expanded", "false");
  }

  // Lý do lỗi hiện dạng popup ngay dưới ô số liệu được bấm, để không chiếm chỗ của bảng khách.
  function toggleReasons(tile) {
    const wasOpen = tile.getAttribute("aria-expanded") === "true";
    hideReasons();
    if (wasOpen) return;
    const errors = batchErrors.filter((e) => e.status === tile.dataset.reason);
    const $box = $("#znsBatchReasons");
    $box
      .html(
        `<div class="zns-batch-reasons-title">Lý do: ${escapeHtml($(tile).find("span").text().trim())}</div>` +
          errors
            .map(
              (e) =>
                `<div class="zns-batch-reason"><span class="zns-reason-count">${formatAmount(e.count)}</span><span>${e.status === "failed" && e.kind_label ? `<b>${escapeHtml(e.kind_label)}:</b> ` : ""}${escapeHtml(e.message || "Không có chi tiết")}</span></div>`,
            )
            .join(""),
      )
      .removeClass("d-none");
    $box.css("left", Math.max(0, Math.min(tile.offsetLeft, $box.parent().innerWidth() - $box.outerWidth())));
    tile.setAttribute("aria-expanded", "true");
  }

  let currentBatch = null;
  function openBatch(id, keepView = false) {
    Loading.wrap(Api.get(EP.batch(id)), APP.MESSAGES.LOADING_SHORT)
      .then((b) => {
        currentBatch = b;
        $("#znsBatchTitle").text(`Lô #${b.id} · ${b.template_name || ""}`);
        $("#znsBatchSub").html(
          [
            ZnsUi.statusBadge(b.status, b.status_label),
            ZnsUi.ownerBadge(b.owner),
            ZnsUi.codeChip(b.zns_code),
            `<span>${escapeHtml(b.file_name)}</span>`,
            `<span>Xác nhận ${formatUtcDateTime(b.confirmed_at)}${b.created_by ? ` · ${escapeHtml(b.created_by)}` : ""}</span>`,
            b.parent_batch_id ? `<span>Gửi lại từ lô #${b.parent_batch_id}</span>` : "",
            b.approved_by ? `<span>Duyệt bởi ${escapeHtml(b.approved_by)} · ${formatUtcDateTime(b.approved_at)}</span>` : "",
          ].join(""),
        );
        const stat = (cls, text, value, reason) =>
          reason && value
            ? `<button type="button" class="zns-stat zns-stat-btn ${cls}" data-reason="${reason}" aria-expanded="false" title="Xem lý do"><span>${text} <i class="fas fa-info-circle" aria-hidden="true"></i></span><b>${formatAmount(value)}</b></button>`
            : `<div class="zns-stat ${cls}"><span>${text}</span><b>${formatAmount(value)}</b></div>`;
        batchErrors = b.error_summary;
        hideReasons();
        $("#znsBatchStats").html(
          stat("", "Tổng", b.total_rows) +
            stat("", "Lỗi dữ liệu", b.invalid_rows, "invalid") +
            stat("is-ok", b.send_mode === "dry_run" ? "Chạy thử" : "Đã gửi", b.sent_rows) +
            stat(b.failed_rows ? "is-bad" : "", "Gửi lỗi", b.failed_rows, "failed") +
            stat(b.unknown_rows ? "is-warn" : "", "Chưa rõ", b.unknown_rows, "unknown") +
            stat("", "Bỏ qua", b.skipped_rows, "skipped"),
        );
        currentBatchId = b.id;
        if (!keepView) $("#znsBatchFilter").val("");
        batchTable.column(0).visible(b.can_skip);
        $("#znsBatchActions").html(batchActions(b));
        const notice = batchNotice(b);
        $("#znsBatchNotice").toggleClass("d-none", !notice).html(notice);
        batchTable.one("draw.dt", () => $("#znsBatchModal").modal("show"));
        batchTable.ajax.reload(null, !keepView);
      })
      .catch((x) => Dialog.error(Api.errorMessage(x, "Không tải được lô gửi.")));
  }

  function batchNotice(b) {
    if (b.status === "paused") {
      return `<i class="fas fa-pause-circle mr-1"></i>${escapeHtml(b.pause_reason || "Lô tạm dừng do lỗi cấu hình liên tiếp. Sửa mẫu tin rồi tạo lô mới, hoặc hủy lô.")}`;
    }
    if (b.status === "rejected")
      return `<i class="fas fa-times-circle mr-1"></i>${escapeHtml(b.rejected_by || "")} đã từ chối: ${escapeHtml(b.reject_reason || "")}`;
    if (b.status !== "pending_approval") return "";
    const a = b.approval;
    const usage =
      a.cap === null
        ? `Đã dùng tháng này: ${formatAmount(a.used)} tin`
        : `Đã dùng tháng này: ${formatAmount(a.used)} / ${formatAmount(a.cap)} tin`;
    const cost = a.est_cost === null ? "" : ` · Ước tính ${formatAmount(a.est_cost)} đ`;
    const self = b.approve_blocked_self ? " · Bạn là người tạo lô nên cần người khác duyệt." : "";
    return `<i class="fas fa-hourglass-half mr-1"></i>Chờ duyệt ${formatAmount(a.count)} tin${cost} · ${usage}${self}`;
  }

  function approveBatch(b) {
    const live = state.sendMode === "live";
    const cost = b.approval.est_cost === null ? "" : `, ước tính ${formatAmount(b.approval.est_cost)} đ`;
    Dialog.confirm({
      title: `Duyệt lô #${b.id}?`,
      message: live
        ? `Hệ thống sẽ gửi tin thật tới ${formatAmount(b.approval.count)} khách ngay sau khi duyệt${cost}. Không hoàn tác được.`
        : `Server đang ở chế độ chạy thử: ${formatAmount(b.approval.count)} khách được đánh dấu "Chạy thử", không có tin nào được gửi.`,
      confirmText: live ? "Duyệt và gửi thật" : "Duyệt",
      cancelText: "Không",
      variant: live ? "danger" : "primary",
    }).then((ok) => {
      if (!ok) return;
      Loading.wrap(Api.postJson(EP.batchApprove(b.id), {}), APP.MESSAGES.LOADING_SHORT)
        .then(() => {
          $("#znsBatchModal").modal("hide");
          Toast.success(`Đã duyệt lô #${b.id}.`);
          reloadHistory();
        })
        .catch((x) => Dialog.error(Api.errorMessage(x)));
    });
  }

  function rejectBatch(b) {
    Dialog.confirm({
      title: `Từ chối lô #${b.id}?`,
      html: true,
      message:
        '<textarea class="form-control form-control-sm" id="znsRejectReason" rows="3" maxlength="500" placeholder="Lý do từ chối (bắt buộc)"></textarea>',
      confirmText: "Từ chối",
      cancelText: "Không",
      variant: "danger",
    }).then((ok) => {
      if (!ok) return;
      Loading.wrap(Api.postJson(EP.batchReject(b.id), { reason: $("#znsRejectReason").val() }), APP.MESSAGES.LOADING_SHORT)
        .then(() => {
          $("#znsBatchModal").modal("hide");
          Toast.success(`Đã từ chối lô #${b.id}.`);
          reloadHistory();
        })
        .catch((x) => Dialog.error(Api.errorMessage(x)));
    });
  }

  function skipCustomers(recipientId, title) {
    Dialog.confirm({
      title,
      html: true,
      message:
        '<div class="small text-muted mb-2">Khách sẽ không còn tính là lỗi và không gửi lại được nữa. Không hoàn tác được.</div><textarea class="form-control form-control-sm" id="znsSkipReason" rows="3" maxlength="500" placeholder="Lý do bỏ qua (bắt buộc)"></textarea>',
      confirmText: "Bỏ qua",
      cancelText: "Không",
      variant: "warning",
    }).then((ok) => {
      if (!ok) return;
      const reason = $("#znsSkipReason").val();
      Loading.wrap(Api.postJson(EP.batchSkip(currentBatchId), { recipient_id: recipientId, reason }), APP.MESSAGES.LOADING_SHORT)
        .then((res) => {
          Toast.success(`Đã bỏ qua ${formatAmount(res.skipped)} khách.`);
          openBatch(currentBatchId, true);
          reloadHistory();
        })
        .catch((x) => Dialog.error(Api.errorMessage(x)));
    });
  }

  function batchActions(b) {
    const options = b.retry_options;
    const approval = b.can_approve
      ? '<button type="button" class="btn btn-sm btn-success" data-approve><i class="fas fa-check mr-1"></i>Duyệt</button><button type="button" class="btn btn-sm btn-outline-danger" data-reject><i class="fas fa-times mr-1"></i>Từ chối</button>'
      : "";
    const button = (retry, count, cls, icon, text) =>
      count
        ? `<button type="button" class="btn btn-sm ${cls}" data-retry="${retry}" data-count="${count}"><i class="fas ${icon} mr-1"></i>${text} (${formatAmount(count)})</button>`
        : "";
    const retries = b.can_retry
      ? button("temporary", options.temporary, "btn-outline-primary", "fa-redo", "Gửi lại lỗi tạm thời") +
        button("unknown", options.unknown, "btn-outline-warning", "fa-question-circle", "Gửi lại chưa rõ") +
        button("new", options.new_batch, "zns-btn-new-batch", "fa-clone", "Tạo lô mới gửi lại")
      : "";
    const errors = b.failed_rows + b.unknown_rows + b.invalid_rows;
    const exportErrors =
      errors && canExportBatch
        ? `<a class="btn btn-sm btn-outline-secondary" href="${Api.url(EP.batchExport(b.id))}?status=errors"><i class="fas fa-file-excel mr-1"></i>Xuất khách lỗi</a>`
        : "";
    const skipAll =
      b.can_skip && b.skip_count
        ? `<button type="button" class="btn btn-sm btn-outline-secondary" data-skip-all data-count="${b.skip_count}"><i class="fas fa-user-slash mr-1"></i>Bỏ qua khách lỗi (${formatAmount(b.skip_count)})</button>`
        : "";
    return approval + retries + skipAll + exportErrors;
  }

  function retryBatch(id, kind, count) {
    const live = state.sendMode === "live";
    const dialogs = {
      temporary: {
        title: `Gửi lại ${formatAmount(count)} khách lỗi tạm thời?`,
        message: "Gửi lại ngay trên lô này, nội dung giữ nguyên. Các khách này chưa nhận được tin do lỗi kết nối hoặc Incom tạm thời lỗi.",
        variant: "primary",
      },
      unknown: {
        title: `Gửi lại ${formatAmount(count)} khách chưa rõ kết quả?`,
        message: "Không biết tin lần trước đã tới các khách này hay chưa. Gửi lại có thể làm khách nhận 2 tin và tốn thêm phí.",
        variant: "warning",
      },
      new: {
        title: `Tạo lô mới cho ${formatAmount(count)} khách?`,
        message:
          "Lô mới dùng nội dung và biến hiện tại của mẫu tin, nên hãy sửa mẫu tin trước. Lô mới sẽ chờ người khác duyệt rồi mới gửi.",
        variant: "primary",
      },
    };
    const dialog = dialogs[kind];
    Dialog.confirm({
      title: dialog.title,
      message: `${dialog.message}${live ? "" : " Server đang ở chế độ chạy thử: không có tin nào được gửi."}`,
      confirmText: "Gửi lại",
      cancelText: "Không",
      variant: dialog.variant,
    }).then((ok) => {
      if (!ok) return;
      const request = kind === "new" ? Api.postJson(EP.batchRetryNew(id), {}) : Api.postJson(EP.batchRetry(id), { kinds: [kind] });
      Loading.wrap(request, APP.MESSAGES.LOADING_SHORT)
        .then((res) => {
          $("#znsBatchModal").modal("hide");
          reloadHistory(res.batch_id !== id);
        })
        .catch((x) => Dialog.error(Api.errorMessage(x)));
    });
  }

  function toggleAttempts() {
    const $row = $(this).closest("tr");
    if ($row.next().hasClass("zns-attempts-row")) return $row.next().remove();
    Api.get(EP.recipientAttempts(currentBatchId, $row.data("id")))
      .done((res) => {
        const lines = (res.data || []).map(
          (a) => `<tr>
            <td>${a.attempt_no}</td>
            <td class="text-nowrap">${formatUtcDateTime(a.created_at)}</td>
            <td>${a.trigger_type === "manual" ? `Gửi lại${a.triggered_by ? ` · ${escapeHtml(a.triggered_by)}` : ""}` : "Tự động"}</td>
            <td>${escapeHtml(a.result_label)}</td>
            <td>${a.http_status === null ? "—" : a.http_status}</td>
            <td>${a.duration_ms === null ? "—" : `${formatAmount(a.duration_ms)} ms`}</td>
            <td class="zns-msg-cell">${escapeHtml(a.error || a.response || "")}</td>
          </tr>`,
        );
        $row.after(
          `<tr class="zns-attempts-row"><td colspan="${$row.children().length}"><table class="table table-sm mb-0">
            <thead><tr><th>Lần</th><th>Lúc</th><th>Kiểu</th><th>Kết quả</th><th>HTTP</th><th>Thời gian</th><th>Chi tiết</th></tr></thead>
            <tbody>${lines.join("") || '<tr><td colspan="7" class="text-muted">Chưa có lần gọi API nào được ghi lại.</td></tr>'}</tbody>
          </table></td></tr>`,
        );
      })
      .fail((x) => Dialog.error(Api.errorMessage(x)));
  }

  function cancelBatch(id) {
    Dialog.confirm({
      title: `Hủy lô #${id}?`,
      message: 'Các khách chưa gửi của lô này sẽ chuyển sang "Đã hủy" (tin đã gửi thì không thu hồi được). Không hoàn tác được.',
      confirmText: "Hủy lô",
      cancelText: "Không",
      variant: "danger",
    }).then((ok) => {
      if (!ok) return;
      Loading.wrap(Api.postJson(EP.batchCancel(id), {}), APP.MESSAGES.LOADING_SHORT)
        .then(() => {
          Toast.success(`Đã hủy lô #${id}.`);
          reloadHistory();
        })
        .catch((x) => Dialog.error(Api.errorMessage(x)));
    });
  }

  $("#znsFile").on("change", function () {
    $("#znsFileName")
      .text(this.files[0] ? this.files[0].name : FILE_PLACEHOLDER)
      .toggleClass("has-file", Boolean(this.files[0]));
  });
  $("#znsUploadForm").on("submit", upload);
  $("#znsOwnerSelect").on("change", () => {
    renderTemplateOptions();
    if (String(state.template || "") !== $("#znsTemplateSelect").val()) selectTemplate();
  });
  $("#znsTemplateSelect").on("change", selectTemplate);
  // Sau khi sửa mẫu tin ở tab khác: lấy lại danh sách mẫu + dữ liệu biến của mẫu đang chọn.
  $("#znsTemplateReload").on("click", function () {
    const $icon = $(this).find("i").addClass("fa-spin");
    loadTemplates(true)
      .done(() => {
        if (String(state.template || "") !== $("#znsTemplateSelect").val()) selectTemplate();
        else evaluate();
      })
      .fail((x) => Toast.error(Api.errorMessage(x, "Không tải được danh sách mẫu tin.")))
      .always(() => $icon.removeClass("fa-spin"));
  });
  $("#znsMapping").on("change", ".zns-map-select", function () {
    state.mapping[this.dataset.key] = this.value === "" ? null : Number(this.value);
    evaluate();
  });
  $("#znsCustomer").on("change", function () {
    state.index = Number(this.value) || 0;
    showCustomer();
  });
  $("#znsCustomerSearch").on("input", filterCustomers);
  $("#znsEvalSummary").on("click", "#znsShowInvalid", () => $("#znsInvalidModal").modal("show"));
  $("#znsPrev").on("click", () => {
    state.index = Math.max(0, state.index - 1);
    showCustomer();
  });
  $("#znsNext").on("click", () => {
    state.index = Math.min(state.filtered.length - 1, state.index + 1);
    showCustomer();
  });
  $("#znsConfirmBtn").on("click", openConfirm);
  $("#znsRestart").on("click", () => {
    if (!state.upload) {
      reset();
      return;
    }
    Dialog.confirm({
      title: "Đặt lại?",
      message: "File đã upload, mẫu tin và cấu hình cột đang chọn sẽ bị bỏ. Lô chưa xác nhận sẽ không được lưu.",
      confirmText: "Đặt lại",
      variant: "warning",
    }).then((ok) => {
      if (!ok) return;
      reset();
    });
  });
  $("#znsHistoryReload").on("click", () => reloadHistory());
  $("#znsHistoryExport").on("click", () => Api.download(EP.batchesExport));
  $("#znsBatchFilter").on("change", () => {
    hideReasons();
    batchTable.ajax.reload(null, true);
  });
  $("#znsBatchRows").on("click", ".zns-attempts-btn", toggleAttempts);
  $("#znsBatchRows").on("click", ".zns-skip-btn", function () {
    const customer = batchTable.row($(this).closest("tr")).data();
    skipCustomers(customer.id, `Bỏ qua khách ${customer.phone || ""}?`);
  });
  $("#znsBatchStats").on("click", ".zns-stat-btn", function () {
    toggleReasons(this);
  });
  $("#znsBatchModal").on("click", (e) => {
    if (!$(e.target).closest(".zns-stat-btn, #znsBatchReasons").length) hideReasons();
  });
  $("#znsBatchActions")
    .on("click", "[data-skip-all]", function () {
      skipCustomers(null, `Bỏ qua ${formatAmount(Number(this.dataset.count))} khách lỗi của lô?`);
    })
    .on("click", "[data-approve]", () => approveBatch(currentBatch))
    .on("click", "[data-reject]", () => rejectBatch(currentBatch));
  $("#znsBatchActions").on("click", "[data-retry]", function () {
    retryBatch(currentBatchId, this.dataset.retry, Number(this.dataset.count));
  });
  $("#znsHistoryRows").on("click", ".zns-batch-view", function () {
    openBatch($(this).closest("tr").data("id"));
  });
  $("#znsHistoryRows").on("click", ".zns-batch-cancel", function () {
    cancelBatch($(this).closest("tr").data("id"));
  });

  loadTemplates().fail(() => $("#znsTemplateSelect").html('<option value="">Không tải được mẫu tin</option>'));
  setStep(1);
})();
