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
    activeBadge,
    ownerBadge,
    codeChip,
    userChip,
    highlight,
    placeholders,
    alertBox,
  };
})();
