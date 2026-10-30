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
      title: live ? "Xác nhận gửi tin thật?" : "Xác nhận gửi tin (chạy thử)?",
      html: true,
      message: `<div class="mb-1">Mẫu: <b>${escapeHtml(t.name)}</b> · ${ZnsUi.codeChip(t.zns_code)} ${ZnsUi.ownerBadge(t.owner)}</div>
        <div class="mb-1">File: ${escapeHtml(state.upload.file_name)}</div>
        <div>Sẽ gửi: <b>${formatAmount(r.summary.valid)}</b> khách hàng${r.summary.invalid ? ` · <span class="text-danger">bỏ qua <b>${formatAmount(r.summary.invalid)}</b> dòng lỗi</span>` : ""}</div>
        ${
          live
            ? '<div class="small text-danger mt-2">Hệ thống sẽ <b>gửi tin thật</b> tới từng khách ngay sau khi xác nhận. Không hoàn tác được (chỉ dừng được các khách chưa gửi).</div>'
            : '<div class="small text-muted mt-2">Server đang ở chế độ <b>chạy thử</b>: không gọi API, không có tin nào được gửi. Khách hợp lệ được đánh dấu "Chạy thử".</div>'
        }`,
      confirmText: live ? "Gửi thật" : "Xác nhận",
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
        loadHistory(1);
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

  // Lô đang gửi chạy ở server: tự làm mới lịch sử tới khi xong.
  let historyTimer = null;
  let historyPage = 1;
  function loadHistory(page = historyPage) {
    clearTimeout(historyTimer);
    const $card = $("#znsHistoryCard").addClass("is-loading");
    Api.get(EP.batches, { page })
      .done((res) => {
        historyPage = res.page;
        $("#znsHistoryPager").html(pagerHtml(res.page, res.pages, res.total, res.page_size, "Lô"));
        const list = res.data || [];
        state.sendMode = res.send_mode;
        $("#znsSendMode")
          .removeClass("d-none")
          .toggleClass("is-live", res.send_mode === "live")
          .text(res.send_mode === "live" ? "Gửi thật" : "Chạy thử · không gửi tin thật");
        if (list.some((b) => b.status === "sending")) historyTimer = setTimeout(() => loadHistory(), 3000);
        $("#znsHistoryRows").html(
          list.length
            ? list
                .map(
                  (b) => `<tr data-id="${b.id}">
          <td>#${b.id}</td>
          <td class="text-nowrap">${formatUtcDateTime(b.confirmed_at)}</td>
          <td>${escapeHtml(b.template_name || "—")}<div class="mt-1">${ZnsUi.codeChip(b.zns_code)}</div></td>
          <td>${ZnsUi.ownerBadge(b.owner)}</td>
          <td class="zns-file-cell">${escapeHtml(b.file_name)}</td>
          <td class="num">${formatAmount(b.total_rows)}</td>
          <td class="num">${formatAmount(b.valid_rows)}</td>
          <td class="num">${formatAmount(b.invalid_rows)}</td>
          <td>${ZnsUi.statusBadge(b.status, b.status_label)}</td>
          <td class="num">${formatAmount(b.sent_rows)}</td>
          <td class="num">${b.failed_rows ? `<span class="text-danger">${formatAmount(b.failed_rows)}</span>` : "0"}</td>
          <td>${ZnsUi.userChip(b.created_by)}</td>
          <td class="zns-actions">
            <button type="button" class="btn btn-sm btn-light zns-batch-view" title="Xem chi tiết"><i class="far fa-eye"></i></button>
            <a class="btn btn-sm btn-light" href="${Api.url(EP.batchExport(b.id))}" title="Xuất Excel"><i class="fas fa-file-excel text-success"></i></a>
            ${
              b.status === "pending" || b.status === "sending"
                ? '<button type="button" class="btn btn-sm btn-light zns-batch-cancel" title="Dừng / hủy các khách chưa gửi"><i class="fas fa-ban text-danger"></i></button>'
                : ""
            }
          </td></tr>`,
                )
                .join("")
            : '<tr><td colspan="13" class="text-center text-muted py-4">Chưa có lô gửi nào</td></tr>',
        );
      })
      .fail((x) =>
        $("#znsHistoryRows").html(
          `<tr><td colspan="13" class="rpt-error">${escapeHtml(Api.errorMessage(x, APP.MESSAGES.LOAD_FAILED_RETRY))}</td></tr>`,
        ),
      )
      .always(() => $card.removeClass("is-loading"));
  }

  // Danh sách khách của lô phân trang phía server (page_size khách / trang).
  function openBatch(id, page = 1) {
    Loading.wrap(Api.get(EP.batch(id), { page }), APP.MESSAGES.LOADING_SHORT)
      .then((b) => {
        $("#znsBatchTitle").text(`Lô #${b.id} · ${b.template_name || ""}`);
        $("#znsBatchSub").html(
          [
            ZnsUi.statusBadge(b.status, b.status_label),
            ZnsUi.ownerBadge(b.owner),
            ZnsUi.codeChip(b.zns_code),
            `<span>${escapeHtml(b.file_name)}</span>`,
            `<span>Xác nhận ${formatUtcDateTime(b.confirmed_at)}${b.created_by ? ` · ${escapeHtml(b.created_by)}` : ""}</span>`,
          ].join(""),
        );
        const stat = (cls, text, value) => `<div class="zns-stat ${cls}"><span>${text}</span><b>${formatAmount(value)}</b></div>`;
        $("#znsBatchStats").html(
          stat("", "Tổng", b.total_rows) +
            stat("", "Lỗi dữ liệu", b.invalid_rows) +
            stat("is-ok", b.send_mode === "dry_run" ? "Chạy thử" : "Đã gửi", b.sent_rows) +
            stat(b.failed_rows ? "is-bad" : "", "Gửi lỗi", b.failed_rows),
        );
        $("#znsBatchRows").html(
          b.recipients
            .map(
              (r) => `<tr><td class="num">${r.row_no}</td><td>${cellText(r.customer)}</td><td>${cellText(r.phone)}</td>
              <td>${ZnsUi.statusBadge(r.status, r.status_label)}</td>
              <td class="zns-msg-cell">${r.error ? `<span class="text-danger">${escapeHtml(r.error)}</span>` : escapeHtml(r.content || "")}</td></tr>`,
            )
            .join(""),
        );
        $("#znsBatchPager")
          .data("id", b.id)
          .html(pagerHtml(b.page, b.pages, b.total_rows, b.page_size, "Khách"));
        $("#znsBatchExport").attr("href", Api.url(EP.batchExport(b.id)));
        $("#znsBatchModal").modal("show");
      })
      .catch((x) => Dialog.error(Api.errorMessage(x, "Không tải được lô gửi.")));
  }

  function pagerHtml(page, pages, total, size, unit) {
    if (pages <= 1) return "";
    const from = (page - 1) * size + 1;
    const to = Math.min(page * size, total);
    const btn = (target, icon, title, disabled) =>
      `<button type="button" class="btn btn-sm btn-light zns-page-btn" data-page="${target}" title="${title}" ${disabled ? "disabled" : ""}><i class="fas ${icon}"></i></button>`;
    return `<span>${unit} ${formatAmount(from)}–${formatAmount(to)} / ${formatAmount(total)}</span>
      <div class="zns-pager-nav">
        ${btn(1, "fa-angle-double-left", "Trang đầu", page === 1)}
        ${btn(page - 1, "fa-angle-left", "Trang trước", page === 1)}
        <span>Trang ${page} / ${pages}</span>
        ${btn(page + 1, "fa-angle-right", "Trang sau", page === pages)}
        ${btn(pages, "fa-angle-double-right", "Trang cuối", page === pages)}
      </div>`;
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
          loadHistory();
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
  $("#znsHistoryReload").on("click", () => loadHistory());
  $("#znsHistoryPager").on("click", ".zns-page-btn", function () {
    loadHistory(Number($(this).data("page")));
  });
  $("#znsBatchPager").on("click", ".zns-page-btn", function () {
    openBatch($("#znsBatchPager").data("id"), Number($(this).data("page")));
  });
  $("#znsHistoryRows").on("click", ".zns-batch-view", function () {
    openBatch($(this).closest("tr").data("id"));
  });
  $("#znsHistoryRows").on("click", ".zns-batch-cancel", function () {
    cancelBatch($(this).closest("tr").data("id"));
  });

  loadTemplates().fail(() => $("#znsTemplateSelect").html('<option value="">Không tải được mẫu tin</option>'));
  loadHistory();
  setStep(1);
})();
