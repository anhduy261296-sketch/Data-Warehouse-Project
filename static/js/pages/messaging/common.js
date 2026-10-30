const ZnsUi = (function () {
  const PLACEHOLDER_RE = /<\s*([A-Za-z][A-Za-z0-9_]*)\s*>/g;

  function statusBadge(status, label) {
    return `<span class="zns-state ${APP.ZNS.STATUS_BADGE[status] || ""}">${escapeHtml(label || status)}</span>`;
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

  return { statusBadge, activeBadge, ownerBadge, codeChip, userChip, highlight, placeholders, alertBox };
})();
