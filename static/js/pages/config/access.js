(function () {
  const EP = ENDPOINTS.config;
  const tableOptions = pagedTableOptions();
  let catalog = [];
  let roles = [];
  let users = [];
  let people = [];

  const fail = (x) => Dialog.error(Api.errorMessage(x));

  // Ma trận quyền dùng chung: các nhóm trang thu gọn được, có đếm số quyền và ô tìm kiếm nên danh sách dài ra vẫn gọn.
  // inherited: quyền có sẵn từ nhóm người dùng, chỉ để xem.
  function renderMatrix($box, checked, inherited = new Set()) {
    const opened = new Set(
      $box
        .find(".cfg-matrix-group.is-open")
        .map((i, group) => group.dataset.key)
        .get(),
    );
    const query = $box.find(".cfg-matrix-search").val() || "";
    $box.data("direct", checked);
    $box.html(
      `<div class="cfg-matrix-tools">
        <input type="search" class="form-control form-control-sm cfg-matrix-search" placeholder="Tìm trang hoặc quyền..." aria-label="Tìm trang hoặc quyền" />
        <button type="button" class="btn btn-sm btn-light cfg-matrix-expand" data-open="1">Mở tất cả</button>
        <button type="button" class="btn btn-sm btn-light cfg-matrix-expand" data-open="0">Thu gọn</button>
      </div>` +
        catalog
          .map(
            (group) => `<div class="cfg-matrix-group ${opened.has(group.label) ? "is-open" : ""}" data-key="${escapeHtml(group.label)}">
            <div class="cfg-matrix-title" role="button" tabindex="0" aria-expanded="${opened.has(group.label)}">
              <i class="fas fa-chevron-right cfg-matrix-chevron" aria-hidden="true"></i>
              <span class="cfg-matrix-name">${escapeHtml(group.label)}</span>
              <span class="cfg-matrix-count"></span>
              <button type="button" class="btn btn-link btn-sm cfg-matrix-all">Chọn hết</button>
            </div>
            <div class="cfg-matrix-body">${group.pages
              .map(
                (page) => `<div class="cfg-matrix-row">
                  <div class="cfg-matrix-page">${escapeHtml(page.label)}</div>
                  <div class="cfg-matrix-perms">${page.perms
                    .map((perm) => {
                      const fromRole = inherited.has(perm.codename);
                      return `<label class="${fromRole ? "is-inherited" : ""}"><input type="checkbox" value="${perm.codename}" ${fromRole || checked.has(perm.codename) ? "checked" : ""} ${fromRole ? "disabled" : ""} />${escapeHtml(perm.label)}</label>`;
                    })
                    .join("")}</div>
                </div>`,
              )
              .join("")}</div>
          </div>`,
          )
          .join(""),
    );
    $box.find(".cfg-matrix-search").val(query);
    filterMatrix($box);
    $box.find(".cfg-matrix-group").each((i, group) => updateMatrixCount($(group)));
  }

  function updateMatrixCount($group) {
    const inputs = $group.find("input");
    const free = inputs.not(":disabled");
    $group.find(".cfg-matrix-count").text(`${inputs.filter(":checked").length}/${inputs.length}`);
    $group.toggleClass("has-checked", inputs.filter(":checked").length > 0);
    $group
      .find(".cfg-matrix-all")
      .text(free.length && free.not(":checked").length === 0 ? "Bỏ hết" : "Chọn hết")
      .prop("disabled", !free.length);
  }

  function filterMatrix($box) {
    const query = normalizeSearchText($box.find(".cfg-matrix-search").val());
    $box.toggleClass("is-searching", Boolean(query));
    $box.find(".cfg-matrix-group").each((i, node) => {
      const $group = $(node);
      const groupHit = normalizeSearchText(node.dataset.key).includes(query);
      let shown = 0;
      $group.find(".cfg-matrix-row").each((j, row) => {
        const hit = !query || groupHit || normalizeSearchText($(row).text()).includes(query);
        $(row).toggleClass("d-none", !hit);
        if (hit) shown += 1;
      });
      $group.toggleClass("d-none", !shown);
    });
  }

  function bindMatrix($box) {
    const toggle = ($group, open) => {
      $group.toggleClass("is-open", open);
      $group.find(".cfg-matrix-title").attr("aria-expanded", String($group.hasClass("is-open")));
    };
    $box
      .on("input", ".cfg-matrix-search", () => filterMatrix($box))
      .on("click", ".cfg-matrix-expand", function () {
        toggle($box.find(".cfg-matrix-group"), this.dataset.open === "1");
      })
      .on("click", ".cfg-matrix-title", function () {
        toggle($(this).closest(".cfg-matrix-group"));
      })
      .on("keydown", ".cfg-matrix-title", function (e) {
        if (e.target !== this || (e.key !== "Enter" && e.key !== " ")) return;
        e.preventDefault();
        toggle($(this).closest(".cfg-matrix-group"));
      })
      .on("click", ".cfg-matrix-all", function (e) {
        e.stopPropagation();
        const $group = $(this).closest(".cfg-matrix-group");
        const free = $group.find("input").not(":disabled");
        free.prop("checked", free.not(":checked").length > 0);
        updateMatrixCount($group);
      })
      .on("change", "input[type=checkbox]", function () {
        updateMatrixCount($(this).closest(".cfg-matrix-group"));
      });
  }

  function filterPicks(input) {
    const query = normalizeSearchText(input.value);
    $(input.dataset.target)
      .find("label")
      .each((i, label) => $(label).toggleClass("d-none", !normalizeSearchText($(label).text()).includes(query)));
  }

  $(document).on("input", ".cfg-pick-search", function () {
    filterPicks(this);
  });

  const matrixValues = ($box) =>
    $box
      .find("input:checked:not(:disabled)")
      .map((i, input) => input.value)
      .get();

  /* Người dùng */
  let usersTable = null;
  let editingUser = null;

  function loadRoles() {
    return Api.get(EP.roles).done((res) => {
      roles = res.data;
      people = res.users;
      catalog = res.catalog;
    });
  }

  function loadUsers() {
    return $.when(loadRoles(), Api.get(EP.users))
      .done((rolesResult, usersResult) => {
        users = usersResult[0].data;
        const $filter = $("#cfgUserGroupFilter");
        const picked = $filter.val() || "";
        $filter.html(
          `<option value="">Tất cả nhóm</option>${roles.map((r) => `<option value="${r.id}">${escapeHtml(r.name)}</option>`).join("")}<option value="none">Chưa có nhóm</option>`,
        );
        $filter.val(picked);
        showUsers();
      })
      .fail(fail);
  }

  function showUsers() {
    const group = $("#cfgUserGroupFilter").val() || "";
    const list = users.filter((u) => !group || (group === "none" ? !u.roles.length : u.roles.includes(Number(group))));
    usersTable.clear().rows.add(list).draw(false);
  }

  function inheritedCodes(roleIds) {
    return new Set(roles.filter((r) => roleIds.includes(r.id)).flatMap((r) => r.perms));
  }

  const pickedRoles = () =>
    $("#cfgRolePicks input:checked")
      .map((i, input) => Number(input.value))
      .get();

  function openUser(user) {
    editingUser = user;
    $("#cfgUserTitle").text(user ? `Sửa người dùng ${user.username}` : "Thêm người dùng");
    $("#cfgUsername")
      .val(user ? user.username : "")
      .prop("disabled", Boolean(user));
    $("#cfgFullName").val(user ? user.full_name : "");
    $("#cfgEmail").val(user ? user.email : "");
    $("#cfgPassword")
      .val("")
      .attr("placeholder", user ? "Để trống nếu giữ nguyên" : "");
    $("#cfgPasswordLabel").text(user ? "Đổi mật khẩu" : "Mật khẩu");
    $("#cfgActive").prop("checked", user ? user.is_active : true);
    $("#cfgSuperNote").toggleClass("d-none", !(user && user.is_superuser));
    const chosen = user ? user.roles : [];
    $("#cfgUserModal .cfg-pick-search").val("");
    $("#cfgUserMatrix").empty();
    $("#cfgRolePicks").html(
      roles
        .map(
          (r) => `<label><input type="checkbox" value="${r.id}" ${chosen.includes(r.id) ? "checked" : ""} />${escapeHtml(r.name)}</label>`,
        )
        .join(""),
    );
    renderMatrix($("#cfgUserMatrix"), new Set(user ? user.perms : []), inheritedCodes(chosen));
    $("#cfgUserModal").modal("show");
  }

  function initUsers() {
    usersTable = $("#cfgUsersTable").DataTable({
      ...tableOptions,
      data: [],
      columns: [
        {
          data: "id",
          className: "cfg-actions",
          render: () => '<button type="button" class="btn btn-sm btn-light cfg-user-edit" title="Sửa"><i class="fas fa-pen"></i></button>',
        },
        { data: "username", render: (v) => escapeHtml(v) },
        { data: "full_name", render: (v) => escapeHtml(v || "—") },
        {
          data: "roles",
          render: (ids, type, u) =>
            (u.is_superuser ? '<span class="cfg-chip is-super">Toàn quyền</span>' : "") +
              roles
                .filter((r) => ids.includes(r.id))
                .map((r) => `<span class="cfg-chip">${escapeHtml(r.name)}</span>`)
                .join("") +
              (u.perms.length ? `<span class="cfg-chip is-extra">+${u.perms.length} quyền riêng</span>` : "") ||
            '<span class="text-muted">Chưa phân quyền</span>',
        },
        { data: "is_active", render: (v) => activeBadge(v) },
        { data: "last_login", render: (v) => (v ? formatUtcDate(v) : "—") },
      ],
    });
    $("#cfgUsersTable tbody").on("click", ".cfg-user-edit", function () {
      openUser(usersTable.row($(this).closest("tr")).data());
    });
    $("#cfgUserAdd").on("click", () => openUser(null));
    bindMatrix($("#cfgUserMatrix"));
    $("#cfgUserGroupFilter").on("change", showUsers);
    $("#cfgRolePicks").on("change", "input", () => {
      const $matrix = $("#cfgUserMatrix");
      // Quyền riêng trùng với quyền của nhóm vừa bật đang bị mờ: vẫn nhớ để bỏ nhóm thì quyền riêng còn nguyên.
      const covered = $matrix
        .find("input:disabled")
        .map((i, input) => input.value)
        .get()
        .filter((code) => $matrix.data("direct").has(code));
      renderMatrix($matrix, new Set([...matrixValues($matrix), ...covered]), inheritedCodes(pickedRoles()));
    });
    $("#cfgUserForm").on("submit", (e) => {
      e.preventDefault();
      Api.postJson(EP.userSave, {
        id: editingUser ? editingUser.id : null,
        username: $("#cfgUsername").val(),
        full_name: $("#cfgFullName").val(),
        email: $("#cfgEmail").val(),
        password: $("#cfgPassword").val(),
        is_active: $("#cfgActive").prop("checked"),
        roles: pickedRoles(),
        perms: matrixValues($("#cfgUserMatrix")),
      })
        .done(() => {
          $("#cfgUserModal").modal("hide");
          Toast.success("Đã lưu người dùng.");
          loadUsers();
        })
        .fail(fail);
    });
    loadUsers();
  }

  const activeBadge = (active) =>
    active ? '<span class="badge badge-success">Hoạt động</span>' : '<span class="badge badge-secondary">Đã khóa</span>';

  /* Nhóm quyền */
  let rolesTable = null;
  let editingRole = null;

  function loadRoleTable() {
    return loadRoles()
      .done(() => rolesTable.clear().rows.add(roles).draw(false))
      .fail(fail);
  }

  function openRole(role) {
    editingRole = role;
    $("#cfgRoleTitle").text(role ? `Sửa nhóm ${role.name}` : "Thêm nhóm người dùng");
    $("#cfgRoleName").val(role ? role.name : "");
    $("#cfgRoleIsDepartment").prop("checked", Boolean(role && role.is_department));
    $("#cfgRoleModal .cfg-pick-search").val("");
    $("#cfgRoleMatrix").empty();
    const members = role ? role.members : [];
    $("#cfgMemberPicks").html(
      people
        .map(
          (u) =>
            `<label><input type="checkbox" value="${u.id}" ${members.includes(u.id) ? "checked" : ""} />${escapeHtml(u.username)}${u.full_name ? ` <span class="text-muted">· ${escapeHtml(u.full_name)}</span>` : ""}${u.is_active ? "" : ' <span class="text-muted">(đã khóa)</span>'}</label>`,
        )
        .join(""),
    );
    updateMemberCount();
    renderMatrix($("#cfgRoleMatrix"), new Set(role ? role.perms : []));
    $("#cfgRoleModal").modal("show");
  }

  function pickedMembers() {
    return $("#cfgMemberPicks input:checked")
      .map((i, input) => Number(input.value))
      .get();
  }

  function updateMemberCount() {
    $("#cfgMemberCount").text(`(${pickedMembers().length} người)`);
  }

  function deleteRole(role) {
    Dialog.confirm({
      title: `Xóa nhóm ${role.name}?`,
      message: "Không hoàn tác được.",
      confirmText: "Xóa",
      cancelText: "Không",
      variant: "danger",
    }).then((ok) => {
      if (!ok) return;
      Api.postJson(EP.roleDelete(role.id), {})
        .done(() => {
          Toast.success("Đã xóa nhóm.");
          loadRoleTable();
        })
        .fail(fail);
    });
  }

  function initRoles() {
    rolesTable = $("#cfgRolesTable").DataTable({
      ...tableOptions,
      data: [],
      columns: [
        {
          data: "id",
          className: "cfg-actions",
          render: () =>
            '<button type="button" class="btn btn-sm btn-light cfg-role-edit" title="Sửa"><i class="fas fa-pen"></i></button> <button type="button" class="btn btn-sm btn-light cfg-role-delete" title="Xóa"><i class="fas fa-trash text-danger"></i></button>',
        },
        { data: "name", render: (v, type, r) => `${escapeHtml(v)}${r.is_department ? ' <span class="cfg-chip">Phòng ban</span>' : ""}` },
        { data: "members", render: (v) => v.length },
        { data: "perms", render: (v) => v.length },
      ],
    });
    const rowRole = (el) => rolesTable.row($(el).closest("tr")).data();
    $("#cfgRolesTable tbody")
      .on("click", ".cfg-role-edit", function () {
        openRole(rowRole(this));
      })
      .on("click", ".cfg-role-delete", function () {
        deleteRole(rowRole(this));
      });
    $("#cfgRoleAdd").on("click", () => openRole(null));
    bindMatrix($("#cfgRoleMatrix"));
    $("#cfgMemberPicks").on("change", "input", updateMemberCount);
    $("#cfgRoleForm").on("submit", (e) => {
      e.preventDefault();
      Api.postJson(EP.roleSave, {
        id: editingRole ? editingRole.id : null,
        name: $("#cfgRoleName").val(),
        is_department: $("#cfgRoleIsDepartment").prop("checked"),
        perms: matrixValues($("#cfgRoleMatrix")),
        members: pickedMembers(),
      })
        .done(() => {
          $("#cfgRoleModal").modal("hide");
          Toast.success("Đã lưu nhóm.");
          loadRoleTable();
          if (usersTable) loadUsers();
        })
        .fail(fail);
    });
    loadRoleTable();
  }

  /* Nhật ký */
  const auditCache = Api.createPageCache();
  let auditTable = null;
  function initAudit() {
    auditTable = $("#cfgAuditTable").DataTable({
      ...tableOptions,
      serverSide: true,
      processing: true,
      ajax: Api.dataTableSource(EP.audit, null, auditCache),
      columns: [
        { data: "created_at", className: "text-nowrap", render: (v) => formatUtcDate(v) },
        { data: "actor", render: (v) => escapeHtml(v) },
        { data: "action_label", render: (v) => escapeHtml(v) },
        { data: "target_id", render: (v, type, r) => escapeHtml([r.target_type, v].filter(Boolean).join(" ")) },
        { data: "detail", render: (v) => escapeHtml(v || "") },
        { data: "ip_address", className: "text-nowrap", render: (v) => escapeHtml(v || "—") },
      ],
    });
  }

  const INIT = { "#cfgUsers": initUsers, "#cfgRoles": initRoles, "#cfgAudit": initAudit };
  const started = new Set();
  function startTab(target) {
    if (started.has(target)) {
      // Quay lại tab Nhật ký: lấy mới vì có thể vừa có thao tác ở tab khác.
      if (target === "#cfgAudit") {
        auditCache.clear();
        auditTable.ajax.reload(null, false);
      }
      return;
    }
    started.add(target);
    INIT[target]();
  }
  $('.cfg-tabs a[data-toggle="tab"]').on("shown.bs.tab", (e) => startTab(e.target.getAttribute("href")));
  $(".cfg-tabs a").first().tab("show");
})();
