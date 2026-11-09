(function () {
  const EP = ENDPOINTS.messaging;
  const FILE_PLACEHOLDER = "Chọn file Excel (.xlsx)";
  const PREVIEW_LIMIT = 10;
  const INVALID_LIMIT = 500;
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

  const templatePicker = searchableSelect($("#znsTemplateSelect"), { placeholder: "Tìm theo tên hoặc mã mẫu...", emptyText: "Không có mẫu tin phù hợp" });

  function autoSelectTemplate(code) {
    const match = code && state.templates.find((t) => String(t.zns_code) === String(code));
    if (!match || state.template === match.id) return false;
    $("#znsOwnerSelect").val(match.owner);
    renderTemplateOptions();
    $("#znsTemplateSelect").val(String(match.id));
    templatePicker.refresh();
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
    const list = owner ? state.templates.filter((t) => t.owner === owner) : [];
    const placeholder = !owner ? "Chọn chủ hàng trước" : list.length ? "Chọn mẫu tin..." : "Không có mẫu đã duyệt đang hoạt động";
    $("#znsTemplateSelect")
      .prop("disabled", !owner)
      .html(
        `<option value="">${placeholder}</option>` +
          list
            .map(
              (t) =>
                `<option value="${t.id}"${String(t.id) === current ? " selected" : ""}>${escapeHtml(t.name)} · ${escapeHtml(t.zns_code)}</option>`,
            )
            .join(""),
      );
    templatePicker.refresh();
  }

  function clearInvalid() {
    $("#znsInvalidPanel").addClass("d-none");
    $("#znsInvalidRows").empty();
  }

  function selectTemplate() {
    const id = Number($("#znsTemplateSelect").val()) || null;
    state.template = id;
    state.mapping = null;
    state.fixed = {};
    if (!id) {
      $("#znsConfig").addClass("d-none");
      $("#znsEvalSummary").empty();
      clearInvalid();
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

  // Vùng dữ liệu biến ẩn cho gọn; thiếu cột thì tự mở vì phải chọn cột mới gửi được.
  function showVars(visible) {
    state.showVars = visible;
    $("#znsVarsCol").toggleClass("d-none", !visible);
    $("#znsToggleVars").text(visible ? "Ẩn dữ liệu biến" : "Xem dữ liệu biến");
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
    const fixedInput = (name, value) =>
      `<input type="text" class="form-control form-control-sm zns-fixed-input" data-key="${escapeHtml(name)}" value="${escapeHtml(value || "")}" maxlength="500" placeholder="Nhập giá trị dùng chung" aria-label="Giá trị dùng chung cho ${escapeHtml(name)}" />`;
    const fixedValue = (v) => {
      const error = res.fixed_errors[v.name];
      // Biến dùng chung chưa có dữ liệu, hoặc đang nhập tay: cho nhập ngay tại đây.
      if (v.name in state.fixed || !(res.fixed[v.name] || {}).input)
        return `<td class="zns-vars-value${error ? " is-missing" : ""}">${fixedInput(v.name, state.fixed[v.name])}${error ? `<div class="small mt-1">${escapeHtml(error)}</div>` : ""}</td>`;
      if (error) return `<td class="zns-vars-value is-missing"><i class="fas fa-exclamation-circle mr-1"></i>${escapeHtml(error)}</td>`;
      const value = (res.fixed[v.name] || {}).display;
      return `<td class="zns-vars-value">${value ? escapeHtml(value) : '<span class="text-muted">—</span>'}</td>`;
    };
    $("#znsMapping").html(
      group("customer", "fa-user", "Theo khách hàng", "Cột từ Excel") +
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
      stat("", "Tổng", s.total) + stat("is-ok", "Hợp lệ", s.valid) + stat(s.invalid ? "is-bad" : "", "Lỗi", s.invalid),
    );
    const errors = res.mapping_errors.concat(
      Object.keys(res.fixed_errors).length
        ? ['Còn biến dùng chung thiếu hoặc sai dữ liệu - nhập ở bảng dữ liệu biến, hoặc bấm "Sửa ở mẫu tin" rồi chọn lại mẫu.']
        : [],
    );
    showVars(Boolean(state.showVars || res.mapping_errors.length || Object.keys(res.fixed_errors).length));
    ZnsUi.alertBox($("#znsEvalErrors"), errors.map(escapeHtml).join("<br>"));
    ZnsUi.alertBox($("#znsEvalWarnings"), (res.warnings || []).map(escapeHtml).join("<br>"), "warning");
    const invalid = res.rows.filter((r) => r.errors.length);
    $("#znsInvalidPanel").toggleClass("d-none", !invalid.length);
    $("#znsInvalidNote").text(
      invalid.length > INVALID_LIMIT ? `· ${formatAmount(INVALID_LIMIT)} / ${formatAmount(invalid.length)} dòng đầu` : "",
    );
    $("#znsInvalidRows").html(
      invalid
        .slice(0, INVALID_LIMIT)
        .map(
          (r) =>
            `<tr><td class="zns-row-no">${r.row_no}</td><td>${cellText(r.phone || r.raw_phone)}</td><td>${cellText(r.customer)}</td><td>${escapeHtml(r.errors.join("; "))}</td></tr>`,
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
      title: live ? "Xác nhận gửi tin?" : "Xác nhận gửi tin (chạy thử)?",
      html: true,
      message: `<div class="mb-1">Chủ hàng: <b>${escapeHtml(t.owner)}</b></div>
        <div class="mb-1">Mẫu: <b>${escapeHtml(t.zns_code)} - ${escapeHtml(t.name)}</b></div>
        <div>Số lượng: <b>${formatAmount(r.summary.valid)}</b> khách hàng</div>`,
      confirmText: "Gửi",
      cancelText: "Quay lại",
      variant: live ? "danger" : "primary",
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
        const msg = `Lô #${res.batch_id} đang gửi ${formatAmount(res.valid)} khách hàng${res.invalid ? `, bỏ qua ${formatAmount(res.invalid)} dòng lỗi` : ""}. Theo dõi ở Lịch sử lô gửi.`;
        reset();
        Toast.success(msg, { title: res.send_mode === "live" ? "Đang gửi tin" : "Đang chạy thử" });
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
    clearInvalid();
    $("#znsOwnerSelect").val("");
    renderTemplateOptions();
    $("#znsMapping").empty();
    showVars(false);
    $("#znsCustomerSearch").val("");
    renderPreview();
    setStep(1);
  }

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
    { data: "confirmed_at", className: "zns-date-cell", render: (v) => formatUtcDate(v) },
    {
      data: "template_name",
      className: "zns-template-cell",
      render: (v, type, b) => {
        const text = escapeHtml([b.zns_code, v].filter(Boolean).join(" - ") || "—");
        // escapeHtml không thoát dấu " nên phải tự thoát khi đưa vào thuộc tính title.
        return `<span title="${text.replace(/"/g, "&quot;")}">${text}</span>`;
      },
    },
    { data: "owner", render: (v) => ZnsUi.ownerBadge(v) },
    { data: "file_name", className: "zns-file-cell", render: (v) => escapeHtml(v) },
    { data: "total_rows", className: "num", render: (v) => formatAmount(v) },
    { data: "valid_rows", className: "num", render: (v) => formatAmount(v) },
    { data: "invalid_rows", className: "num", render: (v) => formatAmount(v) },
    { data: "status", render: (v, type, b) => ZnsUi.statusBadge(v, b.status_label) },
    { data: "sent_rows", className: "num", render: (v) => formatAmount(v) },
    { data: "failed_rows", className: "num", render: (v) => (v ? `<span class="text-danger">${formatAmount(v)}</span>` : "0") },
    { data: "unknown_rows", className: "num", render: (v) => (v ? `<span class="zns-text-warn">${formatAmount(v)}</span>` : "0") },
    { data: "duration_label", className: "zns-duration-col", render: (v) => v || "—" },
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
    if (list.some((b) => b.status === "sending")) {
      historyCache.clear();
      nextPoll();
    }
  }
  function pollHistory() {
    const params = historyTable.ajax.params();
    Api.get(EP.batches, params)
      .done((res) => {
        if (params !== historyTable.ajax.params()) return; // người dùng vừa đổi trang
        if (patchHistoryRows(res.data)) pollIfSending(res.data);
        else reloadHistory();
      })
      .fail(nextPoll); // lỗi mạng thoáng qua: giữ nguyên bảng và thử lại ở nhịp sau
  }

  const historyCache = Api.createPageCache();
  const historyTable = $("#znsHistoryTable")
    .on("xhr.dt", (e, settings, res) => {
      if (!res || !res.send_mode) return;
      state.sendMode = res.send_mode;
      pollIfSending(res.data);
    })
    .DataTable({
      ...pagedTableOptions(),
      serverSide: true,
      processing: true,
      ajax: Api.dataTableSource(EP.batches, null, historyCache),
      columns: HISTORY_COLUMNS,
    });

  function reloadHistory(resetPaging = false) {
    historyCache.clear();
    historyTable.ajax.reload(null, resetPaging);
  }

  let currentBatchId = null;
  let currentBatchSending = false;
  const recipientCache = Api.createPageCache();
  const batchVersions = new Map();
  function syncRecipientCache(b) {
    const version = [b.status, b.sent_rows, b.failed_rows, b.unknown_rows, b.skipped_rows, b.waiting_rows, b.cancelled_rows].join();
    if (batchVersions.get(b.id) !== version) recipientCache.clear();
    batchVersions.set(b.id, version);
    currentBatchSending = b.status === "sending";
  }
  const batchTable = $("#znsBatchTable").DataTable({
    ...pagedTableOptions("zns-scroll"),
    serverSide: true,
    processing: true,
    deferLoading: 0,
    ajax: (d, callback) =>
      Api.dataTableSource(
        EP.batchRecipients(currentBatchId),
        () => ({ status: batchFilter }),
        currentBatchSending ? null : recipientCache,
      )(d, callback),
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
  let batchFilter = "";
  function hideReasons() {
    $("#znsBatchReasons").addClass("d-none");
    $("#znsBatchStats .zns-metric-info").attr("aria-expanded", "false");
  }

  // Lý do lỗi hiện dạng popup ngay dưới ô số liệu được bấm, để không chiếm chỗ của bảng khách.
  function markActiveMetric() {
    $("#znsBatchStats .zns-metric-filter").each(function () {
      $(this).toggleClass("is-active", this.dataset.filter === batchFilter);
    });
  }

  function toggleReasons(tile) {
    const wasOpen = tile.getAttribute("aria-expanded") === "true";
    hideReasons();
    if (wasOpen) return;
    const errors = batchErrors.filter((e) => e.status === tile.dataset.reason);
    const $box = $("#znsBatchReasons");
    $box
      .html(
        `<div class="zns-batch-reasons-title">Lý do: ${escapeHtml(tile.dataset.label)}</div>` +
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

  function openBatch(id, keepView = false) {
    Loading.wrap(Api.get(EP.batch(id)), APP.MESSAGES.LOADING_SHORT)
      .then((b) => {
        $("#znsBatchTitle").text(`Lô #${b.id} · ${b.template_name || ""}`);
        $("#znsBatchSub").html(
          [
            ZnsUi.statusBadge(b.status, b.status_label),
            ZnsUi.ownerBadge(b.owner),
            ZnsUi.codeChip(b.zns_code),
            `<span>${escapeHtml(b.file_name)}</span>`,
            `<span>Xác nhận ${formatUtcDate(b.confirmed_at)}${b.created_by ? ` · ${escapeHtml(b.created_by)}` : ""}</span>`,
            b.parent_batch_id ? `<span>Gửi lại từ lô #${b.parent_batch_id}</span>` : "",
          ].join(""),
        );
        // Số liệu là bộ lọc nhanh của bảng khách; chỉ số cần chú ý mới có màu.
        const metric = (filter, text, value, tone = "", reason = false) =>
          `<span class="zns-metric${value ? ` ${tone}` : " is-zero"}"><button type="button" class="zns-metric-filter" data-filter="${filter}" ${value || !filter ? "" : "disabled"} title="Lọc khách: ${text}">${text} <b>${formatAmount(value)}</b></button>${
            reason && value
              ? `<button type="button" class="zns-metric-info" data-reason="${filter}" data-label="${text}" aria-expanded="false" title="Xem lý do" aria-label="Xem lý do: ${text}"><i class="fas fa-info-circle" aria-hidden="true"></i></button>`
              : ""
          }</span>`;
        batchErrors = b.error_summary;
        hideReasons();
        $("#znsBatchStats").html(
          metric("", "Tổng", b.total_rows) +
            metric("invalid", "Lỗi dữ liệu", b.invalid_rows, "is-bad", true) +
            metric("sent", b.send_mode === "dry_run" ? "Chạy thử" : "Đã gửi", b.sent_rows) +
            metric("failed", "Gửi lỗi", b.failed_rows, "is-bad", true) +
            metric("unknown", "Chưa rõ", b.unknown_rows, "is-warn", true) +
            metric("skipped", "Bỏ qua", b.skipped_rows, "", true) +
            (b.waiting_rows ? metric("waiting", "Chờ gửi", b.waiting_rows) : "") +
            (b.cancelled_rows ? metric("cancelled", "Đã hủy", b.cancelled_rows) : ""),
        );
        currentBatchId = b.id;
        syncRecipientCache(b);
        if (!keepView) batchFilter = "";
        markActiveMetric();
        batchTable.column(0).visible(b.can_skip);
        $("#znsBatchActions").html(batchActions(b));
        $("#znsBatchNotice")
          .toggleClass("d-none", b.status !== "paused")
          .html(
            `<i class="fas fa-pause-circle mr-1"></i>${escapeHtml(b.pause_note || "Lô tạm dừng do lỗi cấu hình liên tiếp. Sửa mẫu tin, chờ duyệt rồi tạo lô mới, hoặc hủy lô.")}`,
          );
        batchTable.one("draw.dt", () => $("#znsBatchModal").modal("show"));
        batchTable.ajax.reload(null, !keepView);
      })
      .catch((x) => Dialog.error(Api.errorMessage(x, "Không tải được lô gửi.")));
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
    const item = (attrs, count, icon, text) =>
      `<button type="button" class="dropdown-item" ${attrs} data-count="${count}"><i class="fas ${icon}"></i><span>${text}</span><b>${formatAmount(count)}</b></button>`;
    const retry = (kind, count, icon, text) => (count ? item(`data-retry="${kind}"`, count, icon, text) : "");
    const retries = b.can_retry
      ? retry("temporary", options.temporary, "fa-redo", "Gửi lại lỗi tạm thời") +
        retry("unknown", options.unknown, "fa-question-circle", "Gửi lại chưa rõ") +
        retry("new", options.new_batch, "fa-clone", "Tạo lô mới gửi lại")
      : "";
    const errors = b.failed_rows + b.unknown_rows + b.invalid_rows;
    const exportErrors =
      errors && canExportBatch
        ? `<a class="btn btn-sm zns-btn-export" href="${Api.url(EP.batchExport(b.id))}?status=errors"><i class="fas fa-file-excel mr-1"></i>Xuất khách lỗi</a>`
        : "";
    const skipAll = b.can_skip && b.skip_count ? item("data-skip-all", b.skip_count, "fa-user-slash", "Bỏ qua khách lỗi") : "";
    const items = retries + skipAll;
    const menu = items
      ? `<div class="dropdown"><button type="button" class="btn btn-sm btn-outline-primary dropdown-toggle" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">Xử lý khách lỗi${b.skip_count ? ` (${formatAmount(b.skip_count)})` : ""}</button><div class="dropdown-menu dropdown-menu-right zns-batch-menu">${items}</div></div>`
      : "";
    return menu + exportErrors;
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
          "Lô mới dùng nội dung và biến hiện tại của mẫu tin, nên hãy sửa mẫu tin trước. Mẫu phải được duyệt trước, và các khách này sẽ được gửi ngay.",
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
    const cacheKey = `attempts:${$row.data("id")}:${batchTable.row($row).data().attempt_count}`;
    const request = recipientCache.has(cacheKey)
      ? $.Deferred().resolve(recipientCache.get(cacheKey))
      : Api.get(EP.recipientAttempts(currentBatchId, $row.data("id"))).done((res) => recipientCache.set(cacheKey, res));
    request
      .done((res) => {
        const lines = (res.data || []).map(
          (a) => `<tr>
            <td>${a.attempt_no}</td>
            <td class="text-nowrap">${formatUtcDate(a.created_at)}</td>
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
  $("#znsToggleVars").on("click", (e) => {
    e.preventDefault();
    showVars(!state.showVars);
  });
  $("#znsMapping").on("change", ".zns-map-select", function () {
    state.mapping[this.dataset.key] = this.value === "" ? null : Number(this.value);
    evaluate();
  });
  $("#znsMapping").on("change", ".zns-fixed-input", function () {
    const value = this.value.trim();
    if (value) state.fixed[this.dataset.key] = value;
    else delete state.fixed[this.dataset.key];
    evaluate();
  });
  $("#znsCustomer").on("change", function () {
    state.index = Number(this.value) || 0;
    showCustomer();
  });
  $("#znsCustomerSearch").on("input", filterCustomers);
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
  $("#znsBatchRows").on("click", ".zns-attempts-btn", toggleAttempts);
  $("#znsBatchRows").on("click", ".zns-skip-btn", function () {
    const customer = batchTable.row($(this).closest("tr")).data();
    skipCustomers(customer.id, `Bỏ qua khách ${customer.phone || ""}?`);
  });
  $("#znsBatchStats").on("click", ".zns-metric-info", function () {
    toggleReasons(this);
  });
  $("#znsBatchStats").on("click", ".zns-metric-filter", function () {
    batchFilter = this.dataset.filter;
    hideReasons();
    markActiveMetric();
    batchTable.ajax.reload(null, true);
  });
  $("#znsBatchModal").on("click", (e) => {
    if (!$(e.target).closest(".zns-metric-info, #znsBatchReasons").length) hideReasons();
  });
  $("#znsBatchActions").on("click", "[data-skip-all]", function () {
    skipCustomers(null, `Bỏ qua ${formatAmount(Number(this.dataset.count))} khách lỗi của lô?`);
  });
  $("#znsBatchActions").on("click", "[data-retry]", function () {
    retryBatch(currentBatchId, this.dataset.retry, Number(this.dataset.count));
  });
  $("#znsHistoryRows").on("click", ".zns-batch-view", function () {
    openBatch($(this).closest("tr").data("id"));
  });
  $("#znsHistoryRows").on("click", ".zns-batch-cancel", function () {
    cancelBatch($(this).closest("tr").data("id"));
  });

  // Mẫu có thể vừa được duyệt hoặc từ chối ở tab khác: quay lại trang thì lấy lại danh sách, mẫu không còn dùng được sẽ tự bỏ chọn.
  $(window).on("focus", () => {
    loadTemplates(true).done(() => {
      if (String(state.template || "") !== $("#znsTemplateSelect").val()) selectTemplate();
    });
  });
  loadTemplates().fail(() => {
    $("#znsTemplateSelect").html('<option value="">Không tải được mẫu tin</option>');
    templatePicker.refresh();
  });
  setStep(1);
})();
