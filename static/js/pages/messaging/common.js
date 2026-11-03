const ZnsUi = (function () {
  const PLACEHOLDER_RE = /<\s*([A-Za-z][A-Za-z0-9_]*)\s*>/g;

  function statusBadge(status, label) {
    const spinner = status === "sending" ? '<i class="zns-state-spin" aria-hidden="true"></i>' : "";
    return `<span class="zns-state ${APP.ZNS.STATUS_BADGE[status] || ""}">${spinner}${escapeHtml(label || status)}</span>`;
  }

  const APPROVAL_BADGE = Object.freeze({ pending: "is-warn", approved: "is-on", rejected: "is-bad" });

  function approvalBadge(status, label, title) {
    return `<span class="zns-state ${APPROVAL_BADGE[status] || ""}" ${title ? `title="${escapeHtml(title)}"` : ""}>${escapeHtml(label)}</span>`;
  }

  // Duyệt / từ chối mẫu tin, dùng chung cho trang danh sách và trang chi tiết. Trả về mẫu sau khi cập nhật.
  function reviewTemplate(t, approve) {
    const EP = ENDPOINTS.messaging;
    return Dialog.confirm(
      approve
        ? {
            title: `Duyệt mẫu ${t.zns_code}?`,
            message: "Sau khi duyệt, mẫu này được dùng để gửi tin. Nếu sửa mẫu thì phải duyệt lại.",
            confirmText: "Duyệt",
            cancelText: "Không",
            variant: "success",
          }
        : {
            title: `Từ chối mẫu ${t.zns_code}?`,
            html: true,
            message:
              '<textarea class="form-control form-control-sm" id="znsRejectReason" rows="3" maxlength="500" placeholder="Lý do từ chối (bắt buộc)"></textarea>',
            confirmText: "Từ chối",
            cancelText: "Không",
            variant: "danger",
          },
    ).then((ok) => {
      if (!ok) return null;
      const request = approve
        ? Api.postJson(EP.templateApprove(t.id), {})
        : Api.postJson(EP.templateReject(t.id), { reason: $("#znsRejectReason").val() });
      return Loading.wrap(request, APP.MESSAGES.LOADING_SHORT).catch((x) => {
        Dialog.error(Api.errorMessage(x));
        return null;
      });
    });
  }

  // Dropdown có ô tìm kiếm cho danh sách dài. Native select vẫn giữ giá trị và phát sự kiện change như cũ.
  function searchableSelect($select, searchPlaceholder) {
    const $combo = $(`<div class="zns-combo">
      <button type="button" class="form-control form-control-sm zns-combo-btn" aria-haspopup="listbox" aria-expanded="false"><span class="zns-combo-text"></span><i class="fas fa-chevron-down" aria-hidden="true"></i></button>
      <div class="zns-combo-panel d-none">
        <input type="search" class="form-control form-control-sm zns-combo-search" autocomplete="off" />
        <ul class="zns-combo-list" role="listbox"></ul>
      </div>
    </div>`);
    $select.addClass("d-none").after($combo);
    const $btn = $combo.find(".zns-combo-btn");
    const $panel = $combo.find(".zns-combo-panel");
    const $search = $combo.find(".zns-combo-search").attr("placeholder", searchPlaceholder);
    const $list = $combo.find(".zns-combo-list");
    const isOpen = () => !$panel.hasClass("d-none");

    function refresh() {
      $btn.find(".zns-combo-text").text($select.find("option:selected").text());
      $btn.prop("disabled", $select.prop("disabled"));
      if ($select.prop("disabled")) close();
    }

    function renderList() {
      const query = normalizeSearchText($search.val());
      const items = $select
        .find("option")
        .toArray()
        .filter((o) => o.value && normalizeSearchText(o.text).includes(query));
      $list.html(
        items.length
          ? items
              .map(
                (o) =>
                  `<li role="option" data-value="${escapeHtml(o.value)}" class="${o.value === $select.val() ? "is-selected" : ""}">${escapeHtml(o.text)}</li>`,
              )
              .join("")
          : '<li class="is-empty">Không có mẫu tin phù hợp</li>',
      );
      $list.find("li[data-value]").first().addClass("is-active");
    }

    function open() {
      $search.val("");
      renderList();
      $panel.removeClass("d-none");
      $btn.attr("aria-expanded", "true");
      $search.trigger("focus");
    }

    function close() {
      $panel.addClass("d-none");
      $btn.attr("aria-expanded", "false");
    }

    function choose(value) {
      close();
      $select.val(value).trigger("change");
      refresh();
      $btn.trigger("focus");
    }

    function moveActive(step) {
      const items = $list.find("li[data-value]");
      if (!items.length) return;
      const next = (items.index(items.filter(".is-active")) + step + items.length) % items.length;
      items.removeClass("is-active").eq(next).addClass("is-active")[0].scrollIntoView({ block: "nearest" });
    }

    $btn.on("click", () => (isOpen() ? close() : open()));
    $search.on("input", renderList).on("keydown", (e) => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        moveActive(e.key === "ArrowDown" ? 1 : -1);
      } else if (e.key === "Enter") {
        e.preventDefault();
        const active = $list.find("li.is-active");
        if (active.length) choose(String(active.data("value")));
      } else if (e.key === "Escape") {
        close();
        $btn.trigger("focus");
      }
    });
    $list.on("mousedown", "li[data-value]", function (e) {
      e.preventDefault();
      choose(String($(this).data("value")));
    });
    $(document).on("mousedown", (e) => {
      if (isOpen() && !$(e.target).closest($combo).length) close();
    });
    refresh();
    return { refresh };
  }

  function activeBadge(active) {
    return active ? '<span class="zns-state is-on">Hoạt động</span>' : '<span class="zns-state">Ngừng hoạt động</span>';
  }

  function ownerBadge(owner) {
    return owner ? `<span class="badge zns-owner zns-owner--${escapeHtml(owner.toLowerCase())}">${escapeHtml(owner)}</span>` : "—";
  }

  function codeChip(code) {
    return code ? `<span class="zns-code">${escapeHtml(code)}</span>` : "—";
  }

  function userChip(name) {
    return name ? `<span class="zns-user"><i class="fas fa-user-circle mr-1"></i>${escapeHtml(name)}</span>` : "—";
  }

  function highlight(content, values) {
    let html = "";
    let last = 0;
    String(content || "").replace(PLACEHOLDER_RE, (match, name, offset) => {
      html += escapeHtml(content.slice(last, offset));
      const key = name.toLowerCase();
      const has = Object.prototype.hasOwnProperty.call(values, key);
      const value = has ? values[key] : match;
      html +=
        has && value !== ""
          ? `<mark class="zns-var">${escapeHtml(value)}</mark>`
          : `<mark class="zns-var zns-var--missing">${escapeHtml(has ? `<${key}>` : match)}</mark>`;
      last = offset + match.length;
      return match;
    });
    return (html + escapeHtml(String(content || "").slice(last))).replace(/\n/g, "<br>");
  }

  function placeholders(content) {
    const names = [];
    String(content || "").replace(PLACEHOLDER_RE, (m, name) => {
      const key = name.toLowerCase();
      if (!names.includes(key)) names.push(key);
      return m;
    });
    return names;
  }

  function alertBox($el, message, kind) {
    if (!message) {
      $el.addClass("d-none").empty();
      return;
    }
    $el
      .removeClass("d-none alert-danger alert-success alert-warning alert-info")
      .addClass(`alert-${kind || "danger"}`)
      .html(message);
  }

  return {
    statusBadge,
    approvalBadge,
    reviewTemplate,
    searchableSelect,
    activeBadge,
    ownerBadge,
    codeChip,
    userChip,
    highlight,
    placeholders,
    alertBox,
  };
})();
