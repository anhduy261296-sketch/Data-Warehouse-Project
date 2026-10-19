const ReportLoader = (function () {
  function create({ setBusy, lockAlways }) {
    let pending = 0;
    let locked = true;
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
