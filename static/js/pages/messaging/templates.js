(function () {
  const EP = ENDPOINTS.messaging;
  const $page = $("#znsTemplatesPage");
  const isStaff = $page.data("staff") === 1;
  const editUrl = (id) => String($page.data("editUrl")).replace(/0\/$/, `${id}/`);
  const $rows = $("#znsTemplateRows");
  const $card = $("#znsTemplatesCard");
  let templates = [];
  const shortTime = (value) => {
    if (!value) return "—";
    const [day, time] = formatUtcDateTime(value).split(" ");
    return `${day}<div class="zns-by">${(time || "").slice(0, 5)}</div>`;
  };

  function load() {
    $card.addClass("is-loading");
    return Api.get(EP.templates)
      .done((res) => {
        templates = res.data || [];
        renderList();
      })
      .fail((x) =>
        $rows.html(`<tr><td colspan="10" class="rpt-error">${escapeHtml(Api.errorMessage(x, APP.MESSAGES.LOAD_FAILED_RETRY))}</td></tr>`),
      )
      .always(() => $card.removeClass("is-loading"));
  }

  function renderList() {
    const owner = $("#znsFilterOwner").val();
    const status = $("#znsFilterStatus").val();
    const q = normalizeSearchText($("#znsFilterSearch").val());
    const list = templates.filter(
      (t) =>
        (!owner || t.owner === owner) &&
        (status === "" || String(Number(t.is_active)) === status) &&
        (!q || normalizeSearchText(`${t.name} ${t.zns_code}`).includes(q)),
    );
    if (!list.length) {
      $rows.html(
        `<tr><td colspan="10" class="text-center text-muted py-4">${templates.length ? "Không có mẫu tin phù hợp" : "Chưa có mẫu tin nào"}</td></tr>`,
      );
      return;
    }
    $rows.html(
      list
        .map(
          (t) => `<tr data-id="${t.id}">
        <td class="zns-actions zns-center">
          <a class="zns-act zns-act--edit" href="${editUrl(t.id)}" data-loading title="${isStaff ? "Xem / chỉnh sửa" : "Xem chi tiết"}"><i class="fas ${isStaff ? "fa-pen" : "fa-eye"}"></i></a>
          ${
            isStaff
              ? `<button type="button" class="zns-mini-switch zns-toggle ${t.is_active ? "is-on" : ""}" role="switch" aria-checked="${t.is_active}" title="${t.is_active ? "Đang hoạt động - bấm để ngừng" : "Đang ngừng - bấm để bật hoạt động"}"><span></span></button>`
              : ""
          }
        </td>
        <td class="zns-code-col">${ZnsUi.codeChip(t.zns_code)}</td>
        <td class="zns-name-col"><a href="${editUrl(t.id)}" data-loading title="Xem chi tiết">${escapeHtml(t.name)}</a></td>
        <td>${ZnsUi.ownerBadge(t.owner)}</td>
        <td class="zns-center" title="${formatAmount(t.batch_count)} lô gửi">${formatAmount(t.message_count)}</td>
        <td>${ZnsUi.activeBadge(t.is_active)}</td>
        <td class="text-nowrap">${shortTime(t.created_at)}</td>
        <td>${ZnsUi.userChip(t.created_by)}</td>
        <td class="text-nowrap">${shortTime(t.updated_at)}</td>
        <td>${ZnsUi.userChip(t.updated_by)}</td>
      </tr>`,
        )
        .join(""),
    );
  }

  function toggleActive(id) {
    const t = templates.find((x) => x.id === id);
    if (!t) return;
    const active = t.is_active;
    t.is_active = !active;
    renderList();
    Api.postJson(EP.templateActive(id), { active: !active }).fail((x) => {
      t.is_active = active;
      renderList();
      Toast.error(Api.errorMessage(x));
    });
  }

  $("#znsReset").on("click", () => {
    $("#znsFilterOwner, #znsFilterStatus").val("");
    $("#znsFilterSearch").val("");
    load();
  });
  $("#znsExport").on("click", () =>
    Api.download(EP.templateExport, {
      owner: $("#znsFilterOwner").val(),
      status: $("#znsFilterStatus").val(),
      q: $("#znsFilterSearch").val().trim(),
    }),
  );
  $("#znsFilterOwner, #znsFilterStatus").on("change", renderList);
  $("#znsFilterSearch").on("input", renderList);
  $rows.on("click", ".zns-toggle", function () {
    toggleActive($(this).closest("tr").data("id"));
  });
  $('[data-toggle="tooltip"]').tooltip();

  load();
})();
