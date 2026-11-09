// Bootstrap bỏ modal-open khi một modal đóng, kể cả lúc modal bên dưới vẫn mở: khi đó trang nền cuộn được còn modal thì không.
$(document).on("hidden.bs.modal", ".modal", () => {
  if ($(".modal.show").length) $(document.body).addClass("modal-open");
});

const Dialog = (function () {
  const VARIANTS = Object.freeze({
    primary: { icon: "fa-question", button: "btn-primary" },
    danger: { icon: "fa-exclamation-triangle", button: "btn-danger" },
    warning: { icon: "fa-exclamation", button: "btn-warning" },
    success: { icon: "fa-check", button: "btn-success" },
    info: { icon: "fa-info", button: "btn-primary" },
  });
  let $modal = null;
  let settle = null;
  let hiding = false;
  let showAfterHidden = null;

  function ensureModal() {
    if ($modal) return $modal;
    $modal = $(`
      <div class="modal fade app-dialog" tabindex="-1" role="dialog" aria-modal="true" aria-labelledby="appDialogTitle">
        <div class="modal-dialog modal-dialog-centered" role="document">
          <div class="modal-content">
            <div class="app-dialog-body">
              <div class="app-dialog-icon"><i class="fas"></i></div>
              <div class="app-dialog-text">
                <h5 class="app-dialog-title" id="appDialogTitle"></h5>
                <div class="app-dialog-message"></div>
              </div>
            </div>
            <div class="app-dialog-actions">
              <button type="button" class="btn btn-light app-dialog-cancel"></button>
              <button type="button" class="btn app-dialog-ok"></button>
            </div>
          </div>
        </div>
      </div>`).appendTo(document.body);
    $modal.on("click", ".app-dialog-ok", () => close(true));
    $modal.on("click", ".app-dialog-cancel", () => close(false));
    $modal.on("shown.bs.modal", () => $modal.find(".app-dialog-ok").trigger("focus"));
    // Bỏ focus trước khi Bootstrap đặt aria-hidden, nếu không trình duyệt báo lỗi vì phần tử đang focus bị ẩn.
    $modal.on("hide.bs.modal", () => {
      hiding = true;
      $modal.find(":focus").trigger("blur");
    });
    $modal.on("hidden.bs.modal", () => {
      hiding = false;
      if (!showAfterHidden) return close(false);
      const show = showAfterHidden;
      showAfterHidden = null;
      show();
    });
    return $modal;
  }

  function close(result) {
    if (!settle) return;
    const resolve = settle;
    settle = null;
    resolve(result);
    $modal.modal("hide");
  }

  function open(options, withCancel) {
    const opts = Object.assign({ title: "", message: "", html: false, variant: "primary" }, options);
    const variant = VARIANTS[opts.variant] || VARIANTS.primary;
    const $m = ensureModal();
    if (settle) close(false);
    const show = () => {
      $m.attr("data-variant", VARIANTS[opts.variant] ? opts.variant : "primary");
      $m.find(".app-dialog-icon i").attr("class", `fas ${opts.icon || variant.icon}`);
      $m.find(".app-dialog-title").text(opts.title).toggleClass("d-none", !opts.title);
      $m.find(".app-dialog-message")[opts.html ? "html" : "text"](opts.message);
      $m.find(".app-dialog-cancel")
        .text(opts.cancelText || "Hủy")
        .toggleClass("d-none", !withCancel);
      $m.find(".app-dialog-ok")
        .text(opts.confirmText || (withCancel ? "Đồng ý" : "Đã hiểu"))
        .attr("class", `btn app-dialog-ok ${variant.button}`);
      $m.modal({ backdrop: withCancel ? "static" : true, keyboard: true }).modal("show");
    };
    return new Promise((resolve) => {
      settle = resolve;
      // Modal chưa đóng xong (gồm cả lúc nền mờ đang tắt) thì lệnh show bị bỏ qua hoặc bị đóng theo: đợi hidden mới mở.
      if (hiding) showAfterHidden = show;
      else show();
    });
  }

  function confirm(options) {
    return open(typeof options === "string" ? { message: options } : options, true);
  }

  function alert(options) {
    return open(typeof options === "string" ? { message: options } : options, false).then(() => undefined);
  }

  function error(message, title) {
    return alert({ title: title || "Không thực hiện được", message, variant: "danger" });
  }

  return { confirm, alert, error };
})();
