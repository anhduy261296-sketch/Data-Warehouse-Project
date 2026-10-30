(function () {
  const EP = ENDPOINTS.messaging;
  const $root = $("#znsEditor");
  const templateId = Number($root.data("id")) || null;
  const readOnly = $root.data("staff") !== 1;
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

  const DATE_PART = /\d{2}\/\d{2}\/\d{4}/;
  const TIME_PART = /\d{1,2}:\d{2}/;

  function sampleValue(v) {
    const base = defaultSamples[v.name] || "";
    const day = (DATE_PART.exec(base) || [new Date().toLocaleDateString("en-GB")])[0];
    if (v.data_type === "date") return day;
    if (v.data_type === "datetime") return `${(TIME_PART.exec(base) || ["22:00"])[0]} ${day}`;
    if (base) return base;
    if (v.data_type === "number") return "50.000";
    return v.label || v.name;
  }

  const VALUE_PLACEHOLDERS = { text: "Nhập dữ liệu", number: "50000", date: "dd/mm/yyyy", datetime: "hh:mm dd/mm/yyyy" };

  function valuePlaceholder(v) {
    const hint = defaultSamples[v.name];
    return hint || VALUE_PLACEHOLDERS[v.data_type];
  }

  function renderSamples() {
    const active = vars.filter((v) => v.is_active && v.name && v.source === "customer");
    active.forEach((v) => {
      if (!(v.name in samples)) samples[v.name] = sampleValue(v);
    });
    const focused = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.sample : null;
    const html = active
      .map(
        (v) => `<label class="zns-sample">
          <span><code>&lt;${escapeHtml(v.name)}&gt;</code>${v.source === "customer" ? '<i class="fas fa-user ml-1" title="Theo từng khách hàng"></i>' : ""}</span>
          <input type="text" class="form-control form-control-sm" data-sample="${escapeHtml(v.name)}" value="${escapeHtml(samples[v.name])}"
            placeholder="${APP.ZNS.TYPES[v.data_type]}" /></label>`,
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
        ? '<span class="badge badge-light zns-readonly-badge"><i class="fas fa-lock mr-1"></i> Chỉ xem (cần quyền staff để sửa)</span>'
        : "",
    );
    document.documentElement.style.setProperty("--zns-head-h", `${$(".zns-editor-head").outerHeight()}px`);
  }

  function renderPreview() {
    renderSamples();
    const values = {};
    const activeVars = vars.filter((v) => v.is_active && v.name);
    activeVars.forEach((v) => (values[v.name] = (v.source === "customer" ? samples[v.name] : v.default_value) || ""));
    const sampleVars = activeVars.filter((v) => v.source === "customer");
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
    const missingData = vars
      .filter((v) => v.is_active && v.name && v.source === "fixed" && v.is_required && !(v.default_value || "").trim())
      .map((v) => v.name);
    const requiredUnused = vars.filter((v) => v.is_active && v.name && v.is_required && !used.includes(v.name)).map((v) => v.name);
    const checks = [
      [Boolean($("#znsName").val().trim() && $("#znsCode").val().trim() && owner), "Đủ tên, mã template và chủ hàng"],
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
        (missingData.length
          ? `<div class="is-warn"><i class="fas fa-exclamation-triangle mr-1"></i>Biến bắt buộc chưa có dữ liệu: ${escapeHtml(missingData.map((n) => `<${n}>`).join(", "))} - chưa gửi được</div>`
          : "") +
        (requiredUnused.length
          ? `<div class="is-warn"><i class="fas fa-exclamation-triangle mr-1"></i>Biến bắt buộc nhưng chưa dùng trong nội dung: ${escapeHtml(requiredUnused.map((n) => `<${n}>`).join(", "))} - khi gửi vẫn phải có giá trị</div>`
          : "") +
        (unused.length
          ? `<div class="is-info"><i class="fas fa-info-circle mr-1"></i>Biến chưa dùng trong nội dung: ${escapeHtml(unused.map((n) => `<${n}>`).join(", "))}</div>`
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
      const $card = $(node).attr("data-index", i).toggleClass("is-off", !v.is_active);
      const saved = Boolean(v.id);
      $card
        .find("[data-field=name]")
        .val(v.name)
        .prop("readonly", saved || readOnly);
      $card.toggleClass("is-customer", v.source === "customer");
      $card
        .find("[data-field=default_value]")
        .val(v.default_value || "")
        .attr("placeholder", valuePlaceholder(v))
        .prop("readonly", readOnly)
        .prop("disabled", !v.is_active);
      $card
        .find("[data-field=data_type]")
        .html(
          Object.entries(APP.ZNS.TYPES)
            .map(([k, l]) => `<option value="${k}">${l}</option>`)
            .join(""),
        )
        .val(v.data_type)
        .prop("disabled", readOnly || v.has_data || !v.is_active)
        .attr("title", !v.is_active ? "Biến đang ngừng dùng" : v.has_data ? "Biến đã có dữ liệu gửi, không đổi kiểu được" : "");
      $card
        .find("[data-field=is_required]")
        .prop("checked", v.is_required)
        .prop("disabled", readOnly || !v.is_active);
      $card
        .find("[data-field=per_customer]")
        .prop("checked", v.source === "customer")
        .prop("disabled", readOnly || !v.is_active);
      $card
        .find(".zns-var-action")
        .html(
          readOnly
            ? ""
            : saved && v.has_data
              ? `<button type="button" class="btn zns-icon-btn zns-var-toggle" title="${v.is_active ? "Khóa biến - ngừng dùng (giữ cột và dữ liệu)" : "Mở khóa - dùng lại biến"}"><i class="fas ${v.is_active ? "fa-lock" : "fa-lock-open"}"></i></button>`
              : `<button type="button" class="btn zns-icon-btn zns-var-remove" title="${saved ? "Xóa biến (chưa có dữ liệu gửi) - xóa hẳn khi bấm Lưu" : "Bỏ biến chưa lưu"}"><i class="far fa-trash-alt"></i></button>`,
        );
      $card
        .find(".zns-var-badges")
        .html(
          [
            '<i class="fas fa-circle zns-flag zns-flag--used zns-used d-none" title="Đang dùng trong nội dung"></i>',
            v.has_data ? '<i class="fas fa-lock zns-flag" title="Đã có dữ liệu gửi: không đổi kiểu được"></i>' : "",
            !v.is_active ? '<span class="zns-flag zns-flag--off" title="Ngừng dùng: giữ cột và dữ liệu">Ngừng</span>' : "",
          ].join(""),
        );
      $vars.append(node);
    });
    renderPreview();
  }

  function fill(t, defaults, defaultContent) {
    template = t;
    samples = {};
    defaultSamples = {};
    (defaults || []).forEach((v) => (defaultSamples[v.name] = v.sample));
    vars = t ? t.variables.map((v) => Object.assign({}, v)) : defaults.map((v) => Object.assign({ is_active: true }, v));
    owner = t ? t.owner : "";
    $("#znsName").val(t ? t.name : "");
    $("#znsCode").val(t ? t.zns_code : "");
    $("#znsContent").val(t ? t.content : defaultContent || "");
    setSegment($("#znsOwner"), owner);
    $("#znsName, #znsCode, #znsContent").prop("readonly", readOnly);
    $("#znsOwner button").prop("disabled", readOnly);
    $root.find(".zns-edit-only").toggleClass("d-none", readOnly);
    const changes = (t && t.changes) || [];
    $("#znsChangesBox").toggleClass("d-none", !changes.length);
    $("#znsChanges").html(
      changes
        .map(
          (c) => `<li><span class="zns-change-time">${formatUtcDateTime(c.changed_at)}</span> · <b>${escapeHtml(c.changed_by || "")}</b>
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
    // File là cấu hình đầy đủ: biến không có trong file bị xóa (hoặc ngừng dùng nếu đã có dữ liệu gửi).
    const fileNames = new Set(data.variables.map((v) => v.name));
    const removed = data.variables.length ? vars.filter((v) => v.name && !fileNames.has(v.name) && v.is_active !== false) : [];
    const varList = (list) => list.map((v) => `<code>&lt;${escapeHtml(v.name)}&gt;</code>`).join(" ");
    const lines = [
      data.zns_code ? `Mã: <b>${escapeHtml(data.zns_code)}</b>` : "",
      data.name && !$("#znsName").val().trim() ? `Tên: <b>${escapeHtml(data.name)}</b>` : "",
      data.owner ? `Chủ hàng: <b>${escapeHtml(data.owner)}</b>` : "",
      data.content ? "Nội dung tin nhắn: <b>thay bằng nội dung trong file</b> (biến có trong nội dung sẽ là bắt buộc)" : "",
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

  function applyImport(data, byName, added, updated, removed) {
    if (data.zns_code) $("#znsCode").val(data.zns_code);
    if (data.name && !$("#znsName").val().trim()) $("#znsName").val(data.name);
    if (data.content) $("#znsContent").val(data.content);
    if (data.owner) {
      owner = data.owner;
      setSegment($("#znsOwner"), owner);
    }
    updated.forEach((iv) => {
      const v = byName.get(iv.name);
      if (!v.has_data) v.data_type = iv.data_type;
      v.source = iv.source;
      if (iv.source === "fixed") v.default_value = iv.default_value || "";
      if (iv.is_required !== null) v.is_required = iv.is_required;
      v.is_active = true;
      delete samples[v.name];
    });
    removed.forEach((v) => {
      if (v.has_data) v.is_active = false;
    });
    vars = vars.filter((v) => v.has_data || !removed.includes(v));
    added.forEach((iv) =>
      vars.push({
        name: iv.name,
        label: iv.label,
        data_type: iv.data_type,
        source: iv.source,
        is_required: Boolean(iv.is_required),
        is_active: true,
        default_value: iv.default_value || "",
      }),
    );
    const order = new Map(data.variables.map((iv, i) => [iv.name, i]));
    vars.sort((a, b) => (order.has(a.name) ? order.get(a.name) : Infinity) - (order.has(b.name) ? order.get(b.name) : Infinity));
    if (data.content) {
      // File không có cột Bắt buộc: biến có trong nội dung là bắt buộc, không dùng thì bỏ bắt buộc.
      const used = ZnsUi.placeholders(data.content);
      const fromFile = new Map(data.variables.map((iv) => [iv.name, iv]));
      vars.forEach((v) => {
        const iv = fromFile.get(v.name);
        if (v.is_active !== false && (!iv || iv.is_required === null)) v.is_required = used.includes(v.name);
      });
    }
    markDirty();
    renderVariables();
    Toast.success(`Đã điền dữ liệu từ file: ${added.length} biến mới, ${updated.length} biến cập nhật, ${removed.length} biến bỏ.`, {
      title: "Nhập từ Excel",
    });
  }

  function addVariable() {
    vars.push({ name: "", label: null, data_type: "text", source: "fixed", is_required: false, is_active: true, default_value: "" });
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
    // Biến cố định chỉ bắt nhập dữ liệu khi tick "Bắt buộc".
    const empty = vars.findIndex(
      (v) => v.is_active !== false && v.is_required && v.source === "fixed" && !String(v.default_value || "").trim(),
    );
    if (empty >= 0) {
      markInvalid(empty, "Nhập dữ liệu cho biến", "default_value");
      showError(
        `Biến "${vars[empty].name}": bắt buộc nhưng chưa nhập dữ liệu (bỏ tick "Bắt buộc", hoặc tick "Theo KH" nếu mỗi khách một giá trị).`,
      );
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
      content: $("#znsContent").val(),
      is_active: template ? template.is_active : newActive,
      variables: vars.map(({ id, name, label, data_type, source, is_required, is_active, default_value }) => ({
        id,
        name: (name || "").trim(),
        label,
        data_type,
        source,
        is_required,
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
        Toast.success("Đã lưu mẫu tin.");
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

  $vars.on("input change", "input[data-field], select[data-field]", function () {
    const v = vars[$(this).closest(".zns-var-card").data("index")];
    const field = this.dataset.field;
    if (field === "name" || field === "default_value") {
      $(this).removeClass("is-invalid").closest(".zns-var-card").removeClass("is-invalid");
    }
    if (field === "name") {
      const clean = this.value.toLowerCase().replace(/[^a-z0-9_]/g, "");
      if (clean !== this.value) this.value = clean;
      v.name = clean;
    } else if (field === "data_type") {
      v.data_type = this.value;
      delete samples[v.name];
      $(this).closest(".zns-var-card").find("[data-field=default_value]").attr("placeholder", valuePlaceholder(v));
    } else if (field === "per_customer") {
      v.source = this.checked ? "customer" : "fixed";
      $(this).closest(".zns-var-card").toggleClass("is-customer", this.checked);
    } else {
      v[field] = this.type === "checkbox" ? this.checked : this.value;
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
      message: "Biến và cột dữ liệu tương ứng sẽ bị xóa hẳn khi bấm Lưu.",
      confirmText: "Xóa biến",
      variant: "danger",
    }).then((ok) => ok && remove());
  });

  $vars.on("click", ".zns-var-toggle", function () {
    const v = vars[$(this).closest(".zns-var-card").data("index")];
    Dialog.confirm(
      v.is_active
        ? {
            title: `Khóa biến <${v.name}>?`,
            message:
              "Biến sẽ ngừng dùng khi gửi tin. Cột và dữ liệu đã gửi vẫn được giữ, có thể mở khóa lại. Thay đổi áp dụng khi bấm Lưu.",
            confirmText: "Khóa biến",
            variant: "warning",
            icon: "fa-lock",
          }
        : {
            title: `Mở khóa biến <${v.name}>?`,
            message: "Biến sẽ được dùng lại khi gửi tin. Thay đổi áp dụng khi bấm Lưu.",
            confirmText: "Mở khóa",
            variant: "success",
            icon: "fa-lock-open",
          },
    ).then((ok) => {
      if (!ok) return;
      v.is_active = !v.is_active;
      markDirty();
      renderVariables();
    });
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
    Toast.success("Đã tạo mẫu tin và bảng dữ liệu riêng cho mẫu.");
    window.history.replaceState(null, "", window.location.pathname);
  }
  const loading = templateId
    ? $.when(Api.get(EP.template(templateId)), Api.get(EP.templates)).then((t, list) => fill(t[0], list[0].defaults || []))
    : Api.get(EP.templates).then((res) => fill(null, res.defaults || [], res.default_content));
  Loading.wrap(loading, APP.MESSAGES.LOADING_SHORT).catch((x) => Toast.error(Api.errorMessage(x, "Không tải được mẫu tin.")));
})();
