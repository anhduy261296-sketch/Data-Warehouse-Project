// Biến <select> thành dropdown có ô tìm kiếm cho danh sách dài. <select> gốc được ẩn đi nhưng vẫn giữ giá trị và phát sự kiện change.
// Đổi giá trị hoặc danh sách option bằng code thì gọi refresh() trên đối tượng trả về.
// options: placeholder (chữ gợi ý ô tìm), emptyText (khi không có kết quả), includeEmpty (hiện cả option value rỗng, ví dụ "Tất cả").
function searchableSelect($select, options) {
  const { placeholder = "Tìm kiếm...", emptyText = "Không có kết quả phù hợp", includeEmpty = false } = options || {};
  const $combo = $(`<div class="searchable-select">
    <button type="button" class="form-control form-control-sm searchable-select-btn" aria-haspopup="listbox" aria-expanded="false"><span class="searchable-select-text"></span><i class="fas fa-chevron-down" aria-hidden="true"></i></button>
    <div class="searchable-select-panel d-none">
      <input type="search" class="form-control form-control-sm searchable-select-search" autocomplete="off" />
      <ul class="searchable-select-list" role="listbox"></ul>
    </div>
  </div>`);
  $select.addClass("d-none").after($combo);
  const $btn = $combo.find(".searchable-select-btn");
  const $panel = $combo.find(".searchable-select-panel");
  const $search = $combo.find(".searchable-select-search").attr("placeholder", placeholder);
  const $list = $combo.find(".searchable-select-list");
  const isOpen = () => !$panel.hasClass("d-none");

  function refresh() {
    $btn.find(".searchable-select-text").text($select.find("option:selected").text());
    $btn.prop("disabled", $select.prop("disabled"));
    if ($select.prop("disabled")) close();
  }

  function renderList() {
    const query = normalizeSearchText($search.val());
    const items = $select
      .find("option")
      .toArray()
      .filter((o) => (includeEmpty || o.value) && normalizeSearchText(o.text).includes(query));
    $list.html(
      items.length
        ? items
            .map(
              (o) =>
                `<li role="option" data-value="${escapeHtml(o.value)}" class="${o.value === $select.val() ? "is-selected" : ""}">${escapeHtml(o.text)}</li>`,
            )
            .join("")
        : `<li class="is-empty">${escapeHtml(emptyText)}</li>`,
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
      if (active.length) choose(String(active.attr("data-value")));
    } else if (e.key === "Escape") {
      close();
      $btn.trigger("focus");
    }
  });
  $list.on("mousedown", "li[data-value]", function (e) {
    e.preventDefault();
    choose(String($(this).attr("data-value")));
  });
  $(document).on("mousedown", (e) => {
    if (isOpen() && !$(e.target).closest($combo).length) close();
  });
  refresh();
  return { refresh };
}
