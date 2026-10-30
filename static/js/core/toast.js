const Toast = (function () {
  const ICONS = Object.freeze({
    success: "fa-check-circle",
    error: "fa-times-circle",
    warning: "fa-exclamation-triangle",
    info: "fa-info-circle",
  });
  const DURATIONS = Object.freeze({ success: 3500, info: 4000, warning: 5000, error: 6000 });
  const MAX_VISIBLE = 4;
  const RESUME_MS = 1500;
  let $stack = null;

  function stack() {
    if (!$stack) $stack = $('<div class="app-toast-stack" aria-live="polite"></div>').appendTo(document.body);
    return $stack;
  }

  function show(type, message, options) {
    const kind = ICONS[type] ? type : "info";
    const opts = Object.assign({ title: "", html: false, duration: DURATIONS[kind] }, options);
    const $toast = $(`
      <div class="app-toast app-toast--${kind}" role="${kind === "error" ? "alert" : "status"}">
        <i class="fas ${ICONS[kind]} app-toast-icon"></i>
        <div class="app-toast-body"><div class="app-toast-title"></div><div class="app-toast-message"></div></div>
        <button type="button" class="app-toast-close" aria-label="Đóng">&times;</button>
        <div class="app-toast-bar"></div>
      </div>`);
    $toast.find(".app-toast-title").text(opts.title).toggleClass("d-none", !opts.title);
    $toast.find(".app-toast-message")[opts.html ? "html" : "text"](message);

    const $all = stack().children(".app-toast:not(.is-out)");
    if ($all.length >= MAX_VISIBLE) $all.first().trigger("toast:dismiss");
    stack().append($toast);
    requestAnimationFrame(() => $toast.addClass("is-in"));

    let timer = null;
    const dismiss = () => {
      clearTimeout(timer);
      $toast.removeClass("is-in").addClass("is-out");
      setTimeout(() => $toast.remove(), 250);
    };
    $toast.on("toast:dismiss", dismiss).on("click", ".app-toast-close", dismiss);
    if (opts.duration > 0) {
      $toast.find(".app-toast-bar").css("animation-duration", `${opts.duration}ms`);
      timer = setTimeout(dismiss, opts.duration);
      $toast
        .on("mouseenter", () => {
          clearTimeout(timer);
          $toast.addClass("is-paused");
        })
        .on("mouseleave", () => {
          $toast.removeClass("is-paused");
          timer = setTimeout(dismiss, RESUME_MS);
        });
    } else {
      $toast.find(".app-toast-bar").remove();
    }
    return { dismiss };
  }

  return {
    show,
    success: (message, options) => show("success", message, options),
    error: (message, options) => show("error", message, options),
    warning: (message, options) => show("warning", message, options),
    info: (message, options) => show("info", message, options),
  };
})();
