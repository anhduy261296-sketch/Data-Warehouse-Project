(function () {
  const EP = ENDPOINTS.config;
  const tableOptions = {
    autoWidth: false,
    ordering: false,
    pageLength: APP.DATATABLE.PAGE_LENGTH,
    lengthMenu: APP.DATATABLE.LENGTH_MENU,
    dom: "<'table-responsive'tr><'d-flex justify-content-between align-items-center flex-wrap mt-2'i<'d-flex align-items-center rpt-pager'lp>>",
    language: { ...APP.DATATABLE.LANGUAGE_VI, info: "Hiển thị _START_ - _END_ của _TOTAL_ dòng" },
  };
  let catalog = [];
  let roles = [];
  let users = [];

  const fail = (x) => Dialog.error(Api.errorMessage(x));

  // Ma trận quyền dùng chung cho vai trò và người dùng. inherited: quyền có sẵn từ vai trò, chỉ để xem.
  function renderMatrix($box, checked, inherited = new Set()) {
    $box.html(
      catalog
        .map(
          (group) => `<div class="cfg-matrix-group">
            <div class="cfg-matrix-title">${escapeHtml(group.label)}</div>
            ${group.pages
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
              .join("")}
          </div>`,
        )
        .join(""),
    );
  }

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
      catalog = res.catalog;
    });
  }

  function loadUsers() {
    return $.when(loadRoles(), Api.get(EP.users))
      .done((rolesResult, usersResult) => {
        users = usersResult[0].data;
        usersTable.clear().rows.add(users).draw(false);
      })
      .fail(fail);
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
    $("#cfgPassword").val("");
    $("#cfgPasswordLabel").text(user ? "Đổi mật khẩu (để trống nếu giữ nguyên)" : "Mật khẩu");
    $("#cfgActive").prop("checked", user ? user.is_active : true);
    $("#cfgSuperNote").toggleClass("d-none", !(user && user.is_superuser));
    const chosen = user ? user.roles : [];
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
                .join("") || '<span class="text-muted">Chưa có vai trò</span>',
        },
        { data: "is_active", render: (v) => activeBadge(v) },
        { data: "last_login", render: (v) => (v ? formatUtcDateTime(v) : "—") },
      ],
      createdRow: (row, u) => {
        row.dataset.id = u.id;
      },
    });
    $("#cfgUsersTable tbody").on("click", ".cfg-user-edit", function () {
      openUser(usersTable.row($(this).closest("tr")).data());
    });
    $("#cfgUserAdd").on("click", () => openUser(null));
    $("#cfgRolePicks").on("change", "input", () => {
      const extras = new Set(matrixValues($("#cfgUserMatrix")));
      renderMatrix($("#cfgUserMatrix"), extras, inheritedCodes(pickedRoles()));
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

  /* Vai trò */
  let rolesTable = null;
  let editingRole = null;

  function loadRoleTable() {
    return loadRoles()
      .done(() => rolesTable.clear().rows.add(roles).draw(false))
      .fail(fail);
  }

  function openRole(role) {
    editingRole = role;
    $("#cfgRoleTitle").text(role ? `Sửa vai trò ${role.name}` : "Thêm vai trò");
    $("#cfgRoleName").val(role ? role.name : "");
    renderMatrix($("#cfgRoleMatrix"), new Set(role ? role.perms : []));
    $("#cfgRoleModal").modal("show");
  }

  function deleteRole(role) {
    Dialog.confirm({
      title: `Xóa vai trò ${role.name}?`,
      message: "Không hoàn tác được.",
      confirmText: "Xóa",
      cancelText: "Không",
      variant: "danger",
    }).then((ok) => {
      if (!ok) return;
      Api.postJson(EP.roleDelete(role.id), {})
        .done(() => {
          Toast.success("Đã xóa vai trò.");
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
        { data: "name", render: (v) => escapeHtml(v) },
        { data: "user_count" },
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
    $("#cfgRoleForm").on("submit", (e) => {
      e.preventDefault();
      Api.postJson(EP.roleSave, {
        id: editingRole ? editingRole.id : null,
        name: $("#cfgRoleName").val(),
        perms: matrixValues($("#cfgRoleMatrix")),
      })
        .done(() => {
          $("#cfgRoleModal").modal("hide");
          Toast.success("Đã lưu vai trò.");
          loadRoleTable();
          if (usersTable) loadUsers();
        })
        .fail(fail);
    });
    loadRoleTable();
  }

  /* Hạn mức */
  function limitCard(l) {
    const value = (v) => (v === null || v === undefined ? "" : v);
    return `<div class="col-lg-6 mb-3"><form class="cfg-limit-card" data-owner="${l.owner}">
      <div class="mb-2"><b>${escapeHtml(l.owner)}</b></div>
      <div class="cfg-limit-usage">Đã dùng tháng này: <b>${formatAmount(l.used)}</b> / ${l.cap === null ? "không giới hạn" : `${formatAmount(l.cap)} tin`}</div>
      <div class="form-row">
        <div class="form-group col-sm-6"><label>Tối đa mỗi lô (tin)</label><input type="number" min="1" class="form-control form-control-sm" name="max_per_batch" value="${value(l.max_per_batch)}" /></div>
        <div class="form-group col-sm-6"><label>Cách tính hạn mức tháng</label>
          <select class="form-control form-control-sm" name="basis">
            <option value="count" ${l.basis === "count" ? "selected" : ""}>Theo số tin</option>
            <option value="budget" ${l.basis === "budget" ? "selected" : ""}>Theo ngân sách</option>
          </select>
        </div>
        <div class="form-group col-sm-4"><label>Tối đa mỗi tháng (tin)</label><input type="number" min="1" class="form-control form-control-sm" name="max_per_month" value="${value(l.max_per_month)}" /></div>
        <div class="form-group col-sm-4"><label>Giá mỗi tin (đ)</label><input type="number" min="0" step="any" class="form-control form-control-sm" name="unit_price" value="${value(l.unit_price)}" /></div>
        <div class="form-group col-sm-4"><label>Ngân sách tháng (đ)</label><input type="number" min="0" step="any" class="form-control form-control-sm" name="max_budget" value="${value(l.max_budget)}" /></div>
      </div>
      <button type="submit" class="btn btn-sm btn-primary">Lưu ${l.owner}</button>
    </form></div>`;
  }

  function loadLimits() {
    Api.get(EP.limits)
      .done((res) => $("#cfgLimitCards").html(res.data.map(limitCard).join("")))
      .fail(fail);
  }

  function initLimits() {
    $("#cfgLimitCards").on("submit", "form", function (e) {
      e.preventDefault();
      const data = { owner: this.dataset.owner };
      $(this)
        .serializeArray()
        .forEach((field) => {
          data[field.name] = field.value;
        });
      Api.postJson(EP.limitsSave, data)
        .done(() => {
          Toast.success("Đã lưu hạn mức.");
          loadLimits();
        })
        .fail(fail);
    });
    loadLimits();
  }

  /* Nhật ký */
  function initAudit() {
    $("#cfgAuditTable").DataTable({
      ...tableOptions,
      serverSide: true,
      processing: true,
      ajax: Api.dataTableSource(EP.audit),
      columns: [
        { data: "created_at", className: "text-nowrap", render: (v) => formatUtcDateTime(v) },
        { data: "actor", render: (v) => escapeHtml(v) },
        { data: "action_label", render: (v) => escapeHtml(v) },
        { data: "target_id", render: (v, type, r) => escapeHtml([r.target_type, v].filter(Boolean).join(" ")) },
        { data: "detail", render: (v) => escapeHtml(v || "") },
      ],
    });
  }

  const INIT = { "#cfgUsers": initUsers, "#cfgRoles": initRoles, "#cfgLimits": initLimits, "#cfgAudit": initAudit };
  const started = new Set();
  function startTab(target) {
    if (started.has(target)) return;
    started.add(target);
    INIT[target]();
  }
  $('.cfg-tabs a[data-toggle="tab"]').on("shown.bs.tab", (e) => startTab(e.target.getAttribute("href")));
  $(".cfg-tabs a").first().tab("show");
})();
