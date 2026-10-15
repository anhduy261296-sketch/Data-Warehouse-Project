/*
 * Khung tai du lieu cho trang bao cao nhieu vung (Bao cao > Ton kho, E-commerce).
 *   - Dem request dang chay -> khoa / mo nut (setBusy) khi tat ca xong.
 *   - Moi vung 1 API rieng; ket qua ve tre cua bo loc cu bi bo qua (so the he "gen").
 *
 *   const loader = ReportLoader.create({ setBusy, lockAlways: true });
 *   loader.next();                                        // bat dau 1 lan tai moi (doi bo loc)
 *   loader.area(["#card1", "#card2"], path, params, (data) => { ... });
 *   $(table).on("preXhr.dt", loader.begin).on("xhr.dt", loader.end);   // bang DataTables cung tinh vao
 *
 * lockAlways = false: chi khoa nut khi goi lock() truoc (vd bam Tim kiem), doi dropdown thi khong khoa.
 */
const ReportLoader = (function () {
  function create({ setBusy, lockAlways }) {
    let pending = 0;
    let locked = true; // lan tai dau tien luon khoa
    let gen = 0;

    function lock() {
      locked = true;
      if (pending) setBusy(true);
    }
    function begin() {
      pending += 1;
      if (locked) setBusy(true);
    }
    function end() {
      pending = Math.max(0, pending - 1);
      if (pending === 0) {
        setBusy(false);
        locked = !!lockAlways;
      }
    }

    function area(selectors, path, params, render) {
      const $cards = $([].concat(selectors).join(", ")).addClass("is-loading");
      $cards.find(".rpt-error").remove();
      const g = gen;
      begin();
      return Api.get(path, params)
        .done((data) => {
          if (g === gen) render(data);
        })
        .always(end)
        .fail(() => $cards.append(`<div class="rpt-error">${APP.MESSAGES.LOAD_FAILED_RETRY}</div>`))
        .always(() => $cards.removeClass("is-loading"));
    }

    return {
      lock,
      begin,
      end,
      area,
      next: () => (gen += 1),
      current: () => gen,
    };
  }

  return { create };
})();
