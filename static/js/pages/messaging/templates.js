(function () {
  const EP = ENDPOINTS.messaging;
  const $page = $("#znsTemplatesPage");
  const canManage = $page.data("canManage") === 1;
  const canDelete = $page.data("canDelete") === 1;
  const editUrl = (id) => String($page.data("editUrl")).replace(/0\/$/, `${id}/`);
  const $rows = $("#znsTemplateRows");
  const $card = $("#znsTemplatesCard");
  let templates = [];

  const rejected = (t) => t.approval_status === "rejected";
  const shared = pagedTableOptions();
  const table = $("#znsTemplateTable").DataTable({
    ...shared,
    data: [],
    language: { ...shared.language, emptyTable: "Không có mẫu tin nào" },
    createdRow: (row, t) => {
      shared.createdRow(row, t);
      row.className = `zns-row--${t.approval_status}`;
      row.title = t.reject_reason ? `${t.approval_label}: ${t.reject_reason}` : t.approval_label;
    },
    columns: [
      {
        data: "id",
        className: "zns-actions",
        render: (id, type, t) => `
          <a class="zns-act zns-act--edit" href="${editUrl(id)}" data-loading title="${canManage ? "Xem / chỉnh sửa" : "Xem chi tiết"}"><i class="fas ${canManage ? "fa-pen" : "fa-eye"}"></i></a>
          ${
            canManage
              ? `<button type="button" class="zns-mini-switch zns-toggle ${t.is_active ? "is-on" : ""}" role="switch" aria-checked="${t.is_active}" ${rejected(t) ? "disabled" : ""} title="${rejected(t) ? "Mẫu bị từ chối: sửa và chờ duyệt lại để bật hoạt động" : t.is_active ? "Đang hoạt động - bấm để ngừng" : "Đang ngừng - bấm để bật hoạt động"}"><span></span></button>`
              : ""
          }
          ${
            canDelete && !t.has_batches
              ? '<button type="button" class="zns-act zns-act--delete zns-delete" title="Xóa mẫu (mẫu chưa có lô gửi)"><i class="far fa-trash-alt"></i></button>'
              : ""
          }
          ${
            t.can_approve
              ? '<button type="button" class="zns-act zns-act--approve zns-review" data-approve="1" title="Duyệt mẫu"><i class="fas fa-check"></i></button><button type="button" class="zns-act zns-act--reject zns-review" data-approve="0" title="Từ chối mẫu"><i class="fas fa-times"></i></button>'
              : ""
          }`,
      },
      { data: "zns_code", className: "zns-code-col", render: (v) => ZnsUi.codeChip(v) },
      { data: "name", className: "zns-name-col", render: (v, type, t) => `<a href="${editUrl(t.id)}" data-loading title="Xem chi tiết">${escapeHtml(v)}</a>` },
      { data: "owner", render: (v) => ZnsUi.ownerBadge(v) },
      { data: "department_name", className: "zns-dept-col", render: (v) => escapeHtml(v || "—") },
      { data: "message_count", render: (v, type, t) => `<span title="${formatAmount(t.batch_count)} lô gửi">${formatAmount(v)}</span>` },
      { data: "is_active", render: (v) => ZnsUi.activeBadge(v) },
      { data: "created_at", className: "text-nowrap", render: (v) => formatUtcDate(v) },
      { data: "created_by", render: (v) => ZnsUi.userChip(v) },
      { data: "updated_at", className: "text-nowrap", render: (v) => formatUtcDate(v) },
      { data: "updated_by", render: (v) => ZnsUi.userChip(v) },
    ],
  });

  function load() {
    $card.addClass("is-loading");
    return Api.get(EP.templates)
      .done((res) => {
        templates = res.data || [];
        renderList(true);
      })
      .fail((x) => Toast.error(Api.errorMessage(x, APP.MESSAGES.LOAD_FAILED_RETRY)))
      .always(() => $card.removeClass("is-loading"));
  }

  function renderList(keepPage = false) {
    const owner = $("#znsFilterOwner").val();
    const status = $("#znsFilterStatus").val();
    const approval = $("#znsFilterApproval").val();
    const q = normalizeSearchText($("#znsFilterSearch").val());
    const list = templates.filter(
      (t) =>
        (!owner || t.owner === owner) &&
        (status === "" || String(Number(t.is_active)) === status) &&
        (!approval || t.approval_status === approval) &&
        (!q || normalizeSearchText(`${t.name} ${t.zns_code}`).includes(q)),
    );
    table.clear().rows.add(list).draw(keepPage ? false : true);
  }

  function toggleActive(id) {
    const t = templates.find((x) => x.id === id);
    if (!t) return;
    const active = t.is_active;
    t.is_active = !active;
    renderList(true);
    Api.postJson(EP.templateActive(id), { active: !active }).fail((x) => {
      t.is_active = active;
      renderList(true);
      Toast.error(Api.errorMessage(x));
    });
  }

  $("#znsReset").on("click", () => {
    $("#znsFilterOwner, #znsFilterStatus, #znsFilterApproval").val("");
    $("#znsFilterSearch").val("");
    load();
  });
  $("#znsExport").on("click", () =>
    Api.download(EP.templateExport, {
      owner: $("#znsFilterOwner").val(),
      status: $("#znsFilterStatus").val(),
      approval: $("#znsFilterApproval").val(),
      q: $("#znsFilterSearch").val().trim(),
    }),
  );
  $("#znsFilterOwner, #znsFilterStatus, #znsFilterApproval").on("change", () => renderList());
  $("#znsFilterSearch").on("input", () => renderList());
  $rows.on("click", ".zns-review", function () {
    const t = templates.find((x) => x.id === $(this).closest("tr").data("id"));
    ZnsUi.reviewTemplate(t, this.dataset.approve === "1").then((saved) => {
      if (!saved) return;
      Toast.success(saved.approval_status === "approved" ? `Đã duyệt mẫu ${saved.zns_code}.` : `Đã từ chối mẫu ${saved.zns_code}.`);
      load();
    });
  });
  $rows.on("click", ".zns-delete", function () {
    const t = templates.find((x) => x.id === $(this).closest("tr").data("id"));
    if (!t) return;
    Dialog.confirm({
      title: `Xóa mẫu ${t.zns_code}?`,
      message: `Mẫu "${t.name}" sẽ không còn hiện trên hệ thống. Thao tác được ghi vào Nhật ký và mã này có thể dùng lại cho mẫu mới.`,
      confirmText: "Xóa mẫu",
      variant: "danger",
    }).then((ok) => {
      if (!ok) return;
      Loading.wrap(Api.postJson(EP.templateDelete(t.id)), "Đang xóa mẫu tin...")
        .then(() => Toast.success(`Đã xóa mẫu ${t.zns_code}.`))
        .catch((x) => Toast.error(Api.errorMessage(x, "Không xóa được mẫu tin.")))
        .then(load);
    });
  });
  $rows.on("click", ".zns-toggle", function () {
    toggleActive($(this).closest("tr").data("id"));
  });
  $('[data-toggle="tooltip"]').tooltip();

  load();
})();
