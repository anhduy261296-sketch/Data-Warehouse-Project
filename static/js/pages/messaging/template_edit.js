(function () {
  const EP = ENDPOINTS.messaging;
  const $root = $("#znsEditor");
  const templateId = Number($root.data("id")) || null;
  const readOnly = $root.data("canManage") !== 1;
  const editUrl = (id) => String($root.data("editUrl")).replace(/0\/$/, `${id}/`);
  const $vars = $("#znsVariables");
  const tpl = document.getElementById("znsVarTpl");
  let template = null;
  let vars = [];
  let owner = "";
  let dirty = false;
  let newActive = true;
  let samples = {};
  let defaultSamples = {};

  function setDirty(value) {
    dirty = value;
    $("#znsSave").prop("disabled", !dirty);
    $("#znsCancel")
      .toggleClass("disabled", !dirty)
      .attr("aria-disabled", String(!dirty))
      .attr("tabindex", dirty ? null : "-1");
  }

  function markDirty() {
    if (!dirty) setDirty(true);
  }

  function confirmLeave(href) {
    Dialog.confirm({
      title: "Bỏ các thay đổi chưa lưu?",
      message: "Những chỉnh sửa trên trang này sẽ mất nếu rời đi mà không bấm Lưu.",
      confirmText: "Bỏ thay đổi",
      cancelText: "Ở lại",
      variant: "warning",
    }).then((ok) => {
      if (!ok) return;
      setDirty(false);
      Loading.show();
      window.location.href = href;
    });
  }

  const sampleValue = (v) => defaultSamples[v.name] || v.label || v.name;

  const perCustomer = (v) => v.source === "customer";

  function valuePlaceholder(v) {
    const hint = defaultSamples[v.name];
    return `${hint ? `vd: ${hint} · ` : ""}để trống = nhập khi gửi`;
  }

  function renderSamples() {
    const active = vars.filter((v) => v.is_active && v.name && perCustomer(v));
    active.forEach((v) => {
      if (!(v.name in samples)) samples[v.name] = sampleValue(v);
    });
    const focused = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.sample : null;
    const html = active
      .map(
        (v) => `<label class="zns-sample">
          <span><code>&lt;${escapeHtml(v.name)}&gt;</code><i class="fas fa-user ml-1" title="Theo từng khách hàng"></i></span>
          <input type="text" class="form-control form-control-sm" data-sample="${escapeHtml(v.name)}" value="${escapeHtml(samples[v.name])}"
            placeholder="Giá trị thử" /></label>`,
      )
      .join("");
    if ($("#znsSamples").data("html") !== html.replace(/value="[^"]*"/g, "")) {
      $("#znsSamples")
        .html(html || '<div class="text-muted small">Chưa có biến</div>')
        .data("html", html.replace(/value="[^"]*"/g, ""));
      if (focused) $(`#znsSamples [data-sample="${focused}"]`).trigger("focus");
    }
  }

  function activeNames() {
    return vars.filter((v) => v.is_active && v.name).map((v) => v.name);
  }

  function renderHeader() {
    const name = $("#znsName").val().trim();
    $("#znsEditorTitle").text(readOnly ? "Chi tiết mẫu tin" : template ? "Chỉnh sửa mẫu tin" : "Thêm mẫu tin mới");
    $("#znsEditorSub span").text(name || (template ? template.name : "mẫu mới"));
    const active = template ? template.is_active : newActive;
    const label = active ? "Hoạt động" : "Ngừng hoạt động";
    $("#znsStatusPill").toggleClass("is-off", !active).toggleClass("d-none", !readOnly).text(label);
    $("#znsActiveSwitch").toggleClass("d-none", readOnly);
    $("#znsActiveInput").prop("checked", active);
    $("#znsActiveLabel").text(label);
    $("#znsPreviewOwner").text(owner ? `${owner} · Zalo Official Account` : "Zalo Official Account");
    $("#znsEditorTools").html(
      readOnly
        ? '<span class="badge badge-light zns-readonly-badge"><i class="fas fa-lock mr-1"></i> Chỉ xem (cần quyền sửa mẫu tin)</span>'
        : "",
    );
    document.documentElement.style.setProperty("--zns-head-h", `${$(".zns-editor-head").outerHeight()}px`);
  }

  function renderPreview() {
    renderSamples();
    const values = {};
    const activeVars = vars.filter((v) => v.is_active && v.name);
    activeVars.forEach((v) => (values[v.name] = (perCustomer(v) ? samples[v.name] : v.default_value) || ""));
    const sampleVars = activeVars.filter(perCustomer);
    $("#znsSampleReset").prop("disabled", !sampleVars.some((v) => samples[v.name] !== sampleValue(v)));
    const content = $("#znsContent").val();
    $("#znsPreview").html(
      content ? ZnsUi.highlight(content, values) : '<span class="text-muted">Nội dung tin nhắn sẽ hiển thị ở đây</span>',
    );
    $("#znsContentCount").text(`${content.length}/2000`);
    const used = ZnsUi.placeholders(content);
    const names = activeNames();
    $("#znsChips").html(
      names
        .map(
          (n) =>
            `<button type="button" class="btn btn-sm zns-chip${used.includes(n) ? " is-used" : ""}" data-name="${escapeHtml(n)}"${readOnly ? " disabled" : ""}>&lt;${escapeHtml(n)}&gt;</button>`,
        )
        .join(""),
    );
    const unknown = used.filter((n) => !names.includes(n));
    const unused = names.filter((n) => !used.includes(n));
    const tags = (list) => escapeHtml(list.map((n) => `<${n}>`).join(", "));
    const askNames = activeVars.filter((v) => !perCustomer(v) && !String(v.default_value || "").trim()).map((v) => v.name);
    const checks = [
      [Boolean($("#znsName").val().trim() && $("#znsCode").val().trim() && owner && $("#znsDepartment").val()), "Đủ tên, mã template, phòng ban và chủ hàng"],
      [Boolean(content.trim()), "Có nội dung tin nhắn"],
      [
        !unknown.length,
        unknown.length ? `Biến chưa khai báo: ${unknown.map((n) => `<${n}>`).join(", ")}` : "Mọi biến trong nội dung đều đã khai báo",
      ],
    ];
    $("#znsChecks").html(
      checks
        .map(
          ([ok, text]) =>
            `<div class="${ok ? "is-ok" : "is-bad"}"><i class="fas ${ok ? "fa-check-circle" : "fa-times-circle"} mr-1"></i>${escapeHtml(text)}</div>`,
        )
        .join("") +
        (askNames.length ? `<div class="is-info"><i class="fas fa-info-circle mr-1"></i>Chưa có dữ liệu, phải nhập khi gửi: ${tags(askNames)}</div>` : "") +
        (unused.length
          ? `<div class="is-warn"><i class="fas fa-exclamation-triangle mr-1"></i>Chưa có trong nội dung: ${tags(unused)} - vẫn gửi cho Incom và phải có dữ liệu, không dùng thì xóa</div>`
          : ""),
    );
    renderHeader();
    $vars.find(".zns-var-card").each(function () {
      const v = vars[$(this).data("index")];
      $(this).find(".zns-used").toggleClass("d-none", !used.includes(v.name));
    });
  }

  function setSegment($seg, value) {
    const $buttons = $seg.find("button");
    $buttons.each(function () {
      const on = this.dataset.value === value;
      $(this).toggleClass("is-on", on).attr("aria-checked", on);
    });
    const index = $buttons.toArray().findIndex((b) => b.dataset.value === value);
    $seg.attr("data-on", index >= 0 ? index : null);
  }

  function renderVariables() {
    $vars.empty();
    $("#znsVarCount").text(vars.length ? `(${vars.filter((v) => v.is_active).length})` : "");
    if (!vars.length) $vars.html('<div class="zns-empty">Chưa có biến nào. Bấm "Thêm biến" để bắt đầu.</div>');
    vars.forEach((v, i) => {
      const node = tpl.content.firstElementChild.cloneNode(true);
      const $card = $(node).attr("data-index", i).toggleClass("is-off", !v.is_active).toggleClass("is-customer", perCustomer(v));
      const saved = Boolean(v.id);
      $card
        .find("[data-field=name]")
        .val(v.name)
        .prop("readonly", saved || readOnly);
      $card
        .find("[data-field=default_value]")
        .val(v.default_value || "")
        .attr("placeholder", valuePlaceholder(v))
        .prop("readonly", readOnly)
        .prop("disabled", !v.is_active);
      $card
        .find("[data-field=per_customer]")
        .prop("checked", perCustomer(v))
        .prop("disabled", readOnly || !v.is_active);
      $card
        .find(".zns-var-action")
        .html(
          readOnly
            ? ""
            : `<button type="button" class="btn zns-icon-btn zns-var-remove" title="${saved ? "Xóa biến - xóa hẳn khi bấm Lưu" : "Bỏ biến chưa lưu"}"><i class="far fa-trash-alt"></i></button>`,
        );
      $card
        .find(".zns-var-badges")
        .html(
          [
            '<i class="fas fa-circle zns-flag zns-flag--used zns-used d-none" title="Đang dùng trong nội dung"></i>',
            !v.is_active ? '<span class="zns-flag zns-flag--off" title="Ngừng dùng: giữ dữ liệu đã gửi">Ngừng</span>' : "",
          ].join(""),
        );
      $vars.append(node);
    });
    renderPreview();
  }

  function renderApproval() {
    const $bar = $("#znsApprovalBar").toggleClass("d-none", !template);
    if (!template) return;
    const texts = {
      pending: `Mẫu đang chờ duyệt, chưa dùng để gửi được${template.submitted_by ? ` · Người gửi duyệt: ${escapeHtml(template.submitted_by)}` : ""}`,
      approved: `Đã duyệt${template.approved_by ? ` bởi ${escapeHtml(template.approved_by)}` : ""}. Nếu lưu thay đổi, mẫu sẽ phải duyệt lại.`,
      rejected: `${escapeHtml(template.rejected_by || "")} đã từ chối: ${escapeHtml(template.reject_reason || "")}. Sửa rồi lưu để gửi duyệt lại.`,
    };
    $bar.attr("data-status", template.approval_status).html(
      `<span>${ZnsUi.approvalBadge(template.approval_status, template.approval_label)} ${texts[template.approval_status] || ""}</span>
        ${
          template.can_approve
            ? '<span class="zns-approval-actions"><button type="button" class="btn btn-sm btn-success zns-review" data-approve="1"><i class="fas fa-check mr-1"></i> Duyệt</button><button type="button" class="btn btn-sm btn-outline-danger zns-review" data-approve="0"><i class="fas fa-times mr-1"></i> Từ chối</button></span>'
            : ""
        }`,
    );
  }

  const codeIsLocked = () => Boolean(template && template.code_locked);

  function fill(t, defaults, defaultContent, departments) {
    template = t;
    renderApproval();
    samples = {};
    defaultSamples = {};
    (defaults || []).forEach((v) => (defaultSamples[v.name] = v.sample));
    vars = t ? t.variables.map((v) => Object.assign({}, v)) : defaults.map((v) => Object.assign({ is_active: true }, v));
    owner = t ? t.owner : "";
    const chosen = t && t.department_id ? t.department_id : departments.length === 1 ? departments[0].id : "";
    $("#znsDepartment")
      .html(
        `<option value="">Chọn phòng ban</option>${departments.map((d) => `<option value="${d.id}">${escapeHtml(d.name)}</option>`).join("")}`,
      )
      .val(String(chosen))
      .prop("disabled", readOnly);
    $("#znsName").val(t ? t.name : "");
    $("#znsCode").val(t ? t.zns_code : "");
    $("#znsContent").val(t ? t.content : defaultContent || "");
    setSegment($("#znsOwner"), owner);
    $("#znsName, #znsContent").prop("readonly", readOnly);
    const codeLocked = Boolean(t && t.code_locked);
    $("#znsCode")
      .prop("readonly", readOnly || codeLocked)
      .attr("title", codeLocked ? "Mẫu đã có lô gửi nên không đổi được mã. Hãy tạo mẫu mới nếu cần dùng mã khác." : "");
    $("#znsOwner button").prop("disabled", readOnly);
    $root.find(".zns-edit-only").toggleClass("d-none", readOnly);
    const changes = (t && t.changes) || [];
    $("#znsChangesBox").toggleClass("d-none", !changes.length);
    $("#znsChanges").html(
      changes
        .map(
          (c) => `<li><span class="zns-change-time">${formatUtcDate(c.changed_at)}</span> · <b>${escapeHtml(c.changed_by || "")}</b>
          ${c.variable ? `<code>&lt;${escapeHtml(c.variable)}&gt;</code>` : ""} ${escapeHtml(c.detail || c.action)}</li>`,
        )
        .join(""),
    );
    renderVariables();
    setDirty(false);
  }

  function confirmImport(data) {
    const byName = new Map(vars.map((v) => [v.name, v]));
    const added = data.variables.filter((v) => !byName.has(v.name));
    const updated = data.variables.filter((v) => byName.has(v.name));
    // File là cấu hình đầy đủ: biến không có trong file bị xóa.
    const fileNames = new Set(data.variables.map((v) => v.name));
    const removed = data.variables.length ? vars.filter((v) => v.name && !fileNames.has(v.name) && v.is_active !== false) : [];
    const varList = (list) => list.map((v) => `<code>&lt;${escapeHtml(v.name)}&gt;</code>`).join(" ");
    const lines = [
      data.zns_code && !codeIsLocked() ? `Mã: <b>${escapeHtml(data.zns_code)}</b>` : "",
      data.name && !$("#znsName").val().trim() ? `Tên: <b>${escapeHtml(data.name)}</b>` : "",
      data.owner ? `Chủ hàng: <b>${escapeHtml(data.owner)}</b>` : "",
      data.department
        ? departmentValue(data.department)
          ? `Phòng ban: <b>${escapeHtml($(`#znsDepartment option[value="${departmentValue(data.department)}"]`).text())}</b>`
          : `Phòng ban <b>${escapeHtml(data.department)}</b> không có hoặc bạn không thuộc phòng này: vui lòng chọn lại sau khi điền.`
        : "",
      data.content ? "Nội dung tin nhắn: <b>thay bằng nội dung trong file</b>" : "",
      added.length ? `Thêm <b>${added.length}</b> biến: ${varList(added)}` : "",
      updated.length ? `Cập nhật <b>${updated.length}</b> biến đã có` : "",
      removed.length ? `Bỏ <b>${removed.length}</b> biến không có trong file: ${varList(removed)}` : "",
    ].filter(Boolean);
    if (!lines.length) {
      Toast.warning("File không có thông tin nào để điền.");
      return;
    }
    Dialog.confirm({
      title: "Điền dữ liệu từ file?",
      html: true,
      message: `<ul class="pl-3 mb-0">${lines.map((l) => `<li>${l}</li>`).join("")}</ul>`,
      confirmText: "Điền dữ liệu",
      variant: "success",
      icon: "fa-file-import",
    }).then((ok) => ok && applyImport(data, byName, added, updated, removed));
  }

  function departmentValue(name) {
    const wanted = normalizeSearchText(String(name || "").trim());
    const option = wanted && $("#znsDepartment option").filter((i, o) => o.value && normalizeSearchText(o.textContent) === wanted)[0];
    return option ? option.value : "";
  }

  function applyImport(data, byName, added, updated, removed) {
    if (data.zns_code && !codeIsLocked()) $("#znsCode").val(data.zns_code);
    if (data.name && !$("#znsName").val().trim()) $("#znsName").val(data.name);
    if (data.content) $("#znsContent").val(data.content);
    if (data.owner) {
      owner = data.owner;
      setSegment($("#znsOwner"), owner);
    }
    if (departmentValue(data.department)) $("#znsDepartment").val(departmentValue(data.department));
    updated.forEach((iv) => {
      const v = byName.get(iv.name);
      v.data_type = iv.data_type;
      v.source = iv.source;
      v.default_value = iv.default_value || "";
      v.is_active = true;
      delete samples[v.name];
    });
    vars = vars.filter((v) => !removed.includes(v));
    added.forEach((iv) =>
      vars.push({
        name: iv.name,
        label: iv.label,
        data_type: iv.data_type,
        source: iv.source,
        is_active: true,
        default_value: iv.default_value || "",
      }),
    );
    const order = new Map(data.variables.map((iv, i) => [iv.name, i]));
    vars.sort((a, b) => (order.has(a.name) ? order.get(a.name) : Infinity) - (order.has(b.name) ? order.get(b.name) : Infinity));
    markDirty();
    renderVariables();
    Toast.success(`Đã điền dữ liệu từ file: ${added.length} biến mới, ${updated.length} biến cập nhật, ${removed.length} biến bỏ.`, {
      title: "Nhập từ Excel",
    });
  }

  function addVariable() {
    vars.push({ name: "", label: null, data_type: "text", source: "fixed", is_active: true, default_value: "" });
    markDirty();
    renderVariables();
    $vars.find(".zns-var-card:last input[data-field=name]").trigger("focus");
  }

  const NAME_RE = /^[a-z][a-z0-9_]{0,49}$/;
  const SYSTEM_NAMES = ["id", "batchid", "recipientid", "phone", "createdat"];

  function nameError(v, index) {
    if (!NAME_RE.test(v.name || "")) return v.name ? "Chỉ gồm chữ thường không dấu, số, dấu _ và bắt đầu bằng chữ" : "Nhập tên biến";
    if (SYSTEM_NAMES.includes(v.name.replace(/_/g, ""))) return `"${v.name}" là tên cột hệ thống, hãy đặt tên khác`;
    if (vars.some((o, i) => i < index && o.name === v.name)) return `Tên "${v.name}" bị trùng với biến đã có`;
    return "";
  }

  function markInvalid(index, text, field) {
    const $card = $vars.find(`.zns-var-card[data-index="${index}"]`);
    $card
      .addClass("is-invalid")
      .find(`[data-field=${field || "name"}]`)
      .addClass("is-invalid")
      .siblings(".invalid-feedback")
      .text(text);
    $card[0].scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function showError(text) {
    Toast.error(text, { title: "Chưa lưu được" });
  }

  function validate() {
    vars = vars.filter((v) => v.id || (v.name || "").trim());
    renderVariables();
    const index = vars.findIndex((v, i) => nameError(v, i));
    if (index >= 0) {
      const text = nameError(vars[index], index);
      markInvalid(index, text);
      showError(`Biến thứ ${index + 1}: ${text}.`);
      return false;
    }
    return true;
  }

  function save() {
    if (!validate()) return;
    const payload = {
      id: template ? template.id : null,
      name: $("#znsName").val(),
      zns_code: $("#znsCode").val(),
      owner,
      department_id: Number($("#znsDepartment").val()) || null,
      content: $("#znsContent").val(),
      is_active: template ? template.is_active : newActive,
      variables: vars.map(({ id, name, label, data_type, source, is_active, default_value }) => ({
        id,
        name: (name || "").trim(),
        label,
        data_type,
        source,
        is_active,
        default_value: source === "fixed" ? default_value || "" : null,
      })),
    };
    Loading.wrap(Api.postJson(EP.templateSave, payload), "Đang lưu mẫu tin...")
      .then((t) => {
        setDirty(false);
        if (!template) {
          window.location.href = `${editUrl(t.id)}?saved=1`;
          return;
        }
        const keep = Object.assign({}, samples);
        fill(
          t,
          Object.entries(defaultSamples).map(([name, sample]) => ({ name, sample })),
        );
        samples = keep;
        renderPreview();
        Toast.success(t.approval_status === "pending" ? "Đã lưu, mẫu tin đang chờ duyệt." : "Đã lưu mẫu tin.");
      })
      .catch((x) => {
        const text = Api.errorMessage(x, "Không lưu được mẫu tin.");
        showError(text);
        const m = /Biến "([^"]+)"/.exec(text);
        const index = m ? vars.findIndex((v) => v.name === m[1]) : -1;
        if (index >= 0) markInvalid(index, text, text.includes(": dữ liệu") ? "default_value" : "name");
        else window.scrollTo({ top: 0, behavior: "smooth" });
      });
  }

  $("#znsApprovalBar").on("click", ".zns-review", function () {
    if (dirty) {
      Toast.error("Hãy lưu thay đổi trước khi duyệt.");
      return;
    }
    ZnsUi.reviewTemplate(template, this.dataset.approve === "1").then((saved) => {
      if (!saved) return;
      template = saved;
      renderApproval();
      renderHeader();
      Toast.success(saved.approval_status === "approved" ? "Đã duyệt mẫu tin." : "Đã từ chối mẫu tin.");
    });
  });

  function toggleActive() {
    const active = template.is_active;
    template.is_active = !active;
    renderHeader();
    Api.postJson(EP.templateActive(template.id), { active: !active }).fail((x) => {
      template.is_active = active;
      renderHeader();
      Toast.error(Api.errorMessage(x));
    });
  }

  $vars.on("input change", "input[data-field]", function () {
    const v = vars[$(this).closest(".zns-var-card").data("index")];
    const field = this.dataset.field;
    if (field === "name" || field === "default_value") {
      $(this).removeClass("is-invalid").closest(".zns-var-card").removeClass("is-invalid");
    }
    if (field === "name") {
      const clean = this.value.toLowerCase().replace(/[^a-z0-9_]/g, "");
      if (clean !== this.value) this.value = clean;
      v.name = clean;
    } else if (field === "per_customer") {
      v.source = this.checked ? "customer" : "fixed";
      $(this).closest(".zns-var-card").toggleClass("is-customer", this.checked);
    } else {
      v[field] = this.value;
    }
    markDirty();
    renderPreview();
  });
  $("#znsSamples").on("input", "[data-sample]", function () {
    samples[this.dataset.sample] = this.value;
    renderPreview();
  });
  $("#znsSampleReset").on("click", () => {
    samples = {};
    $("#znsSamples").removeData("html");
    renderPreview();
  });
  $vars.on("click", ".zns-var-remove", function () {
    const index = $(this).closest(".zns-var-card").data("index");
    const v = vars[index];
    const remove = () => {
      vars.splice(index, 1);
      markDirty();
      renderVariables();
    };
    if (!v.id) {
      remove();
      return;
    }
    Dialog.confirm({
      title: `Xóa biến <${v.name}>?`,
      message: "Biến sẽ bị xóa khỏi mẫu khi bấm Lưu. Các tin đã gửi không bị ảnh hưởng. Mẫu sẽ phải duyệt lại.",
      confirmText: "Xóa biến",
      variant: "danger",
    }).then((ok) => ok && remove());
  });

  document.addEventListener(
    "click",
    (e) => {
      if (!dirty || readOnly || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const link = e.target.closest("a[href]");
      if (
        !link ||
        (link.target && link.target !== "_self") ||
        link.hasAttribute("download") ||
        link.getAttribute("href").startsWith("#") ||
        link.origin !== window.location.origin
      )
        return;
      e.preventDefault();
      e.stopPropagation();
      confirmLeave(link.href);
    },
    true,
  );

  $("#znsOwner").on("click", "button", function () {
    owner = this.dataset.value;
    setSegment($("#znsOwner"), owner);
    markDirty();
    renderPreview();
  });
  $("#znsChips").on("click", ".zns-chip", function () {
    const el = document.getElementById("znsContent");
    const token = `<${$(this).data("name")}>`;
    const start = el.selectionStart ?? el.value.length;
    el.value = el.value.slice(0, start) + token + el.value.slice(el.selectionEnd ?? start);
    el.focus();
    el.selectionStart = el.selectionEnd = start + token.length;
    markDirty();
    renderPreview();
  });
  $("#znsName, #znsCode, #znsContent").on("input", () => {
    markDirty();
    renderPreview();
  });
  $("#znsDepartment").on("change", () => {
    markDirty();
    renderPreview();
  });
  $("#znsAddVariable").on("click", addVariable);
  $("#znsImportBtn").on("click", () => $("#znsImportFile").val("").trigger("click"));
  $("#znsImportFile").on("change", function () {
    const file = this.files[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    Loading.wrap(Api.upload(EP.templateImport, form), "Đang đọc file Excel...")
      .then(confirmImport)
      .catch((x) => Toast.error(Api.errorMessage(x, "Không đọc được file."), { title: "Không nhập được" }));
  });
  const $head = $(".zns-editor-head");
  const syncHeadHeight = () => document.documentElement.style.setProperty("--zns-head-h", `${$head.outerHeight()}px`);
  syncHeadHeight();
  window.addEventListener("resize", syncHeadHeight);
  window.addEventListener("scroll", () => $head.toggleClass("is-stuck", window.scrollY > 8), { passive: true });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s" && !readOnly) {
      e.preventDefault();
      if (dirty) save();
    }
  });
  $("#znsSave").on("click", save);
  $("#znsActiveInput").on("change", function () {
    if (template) {
      toggleActive();
      return;
    }
    newActive = this.checked;
    markDirty();
    renderHeader();
  });
  window.addEventListener("beforeunload", (e) => {
    if (dirty && !readOnly) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  if (new URLSearchParams(window.location.search).get("saved")) {
    Toast.success("Đã tạo mẫu tin.");
    window.history.replaceState(null, "", window.location.pathname);
  }
  const loading = templateId
    ? $.when(Api.get(EP.template(templateId)), Api.get(EP.templates)).then((t, list) => fill(t[0], list[0].defaults || [], undefined, list[0].departments || []))
    : Api.get(EP.templates).then((res) => fill(null, res.defaults || [], res.default_content, res.departments || []));
  Loading.wrap(loading, APP.MESSAGES.LOADING_SHORT).catch((x) => Toast.error(Api.errorMessage(x, "Không tải được mẫu tin.")));
})();
