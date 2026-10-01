













const Loading = (function () {
  let pending = 0;
  let overlay = null;
  let messageEl = null;

  function ensureOverlay() {
    if (overlay) return;
    overlay = document.createElement("div");
    overlay.className = "app-loading";
    overlay.setAttribute("role", "status");
    overlay.setAttribute("aria-live", "polite");
    overlay.innerHTML =
      '<div class="app-loading__spinner"></div><div class="app-loading__message"></div>';
    messageEl = overlay.querySelector(".app-loading__message");
    document.body.appendChild(overlay);
  }

  function show(message) {
    ensureOverlay();
    pending += 1;
    messageEl.textContent = message || "";
    overlay.classList.add("is-visible");
    document.body.setAttribute("aria-busy", "true");
  }

  function hide() {
    if (pending === 0) return;
    pending -= 1;
    if (pending === 0) {
      overlay.classList.remove("is-visible");
      document.body.removeAttribute("aria-busy");
    }
  }

  
  function reset() {
    pending = 0;
    if (overlay) {
      overlay.classList.remove("is-visible");
      document.body.removeAttribute("aria-busy");
    }
  }

  function isActive() {
    return pending > 0;
  }

  
  async function wrap(task, message) {
    show(message);
    try {
      return await (typeof task === "function" ? task() : task);
    } finally {
      hide();
    }
  }

  
  
  
  
  async function wrapPage(task, message) {
    if (!isActive()) show(message);
    try {
      return await (typeof task === "function" ? task() : task);
    } finally {
      hide();
    }
  }

  function bindDeclarative() {
    document.addEventListener("submit", function (event) {
      const form = event.target;
      if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-loading")) return;
      
      if (isActive()) {
        event.preventDefault();
        return;
      }
      show(form.getAttribute("data-loading-message"));
    });

    document.addEventListener("click", function (event) {
      if (event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const el = event.target.closest("a[data-loading], button[data-loading]");
      if (!el) return;
      if (el.tagName === "A") {
        const target = el.getAttribute("target");
        const href = el.getAttribute("href");
        if ((target && target !== "_self") || !href || href.startsWith("#")) return;
      }
      if (isActive()) {
        event.preventDefault();
        return;
      }
      show(el.getAttribute("data-loading-message"));
    });

    
    
    window.addEventListener("pageshow", function (event) {
      if (event.persisted) reset();
    });
  }

  bindDeclarative();

  return { show, hide, wrap, wrapPage, reset, isActive };
})();
