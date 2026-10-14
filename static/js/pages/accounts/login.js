/* Trang Đăng nhập (templates/accounts/login.html): hien/an mat khau, bat nut Dang nhap khi du thong tin, doi ma captcha. */
(function () {
  const input = document.getElementById("loginPassword");
  const toggle = document.getElementById("loginTogglePassword");
  toggle.addEventListener("click", function () {
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    const label = show ? "Ẩn mật khẩu" : "Hiện mật khẩu";
    toggle.setAttribute("aria-label", label);
    toggle.title = label;
    toggle.querySelector("i").className = show ? "fas fa-eye-slash" : "fas fa-eye";
    input.focus();
  });
  input.form.addEventListener("submit", function () {
    input.type = "password";
  });

  const submit = document.getElementById("loginSubmit");
  const required = ["loginUsername", "loginPassword", "loginCaptcha"].map((id) => document.getElementById(id));
  const updateSubmit = () => {
    const ready = required.every((el) => el.value.trim() !== "") && /^[0-9]{4}$/.test(required[2].value.trim());
    submit.disabled = !ready;
    submit.title = ready ? "" : "Nhập đủ tên đăng nhập, mật khẩu và 4 số mã xác nhận";
  };
  required.forEach((el) => ["input", "change", "keyup"].forEach((ev) => el.addEventListener(ev, updateSubmit)));
  window.addEventListener("load", () => setTimeout(updateSubmit, 300));
  updateSubmit();

  const img = document.getElementById("loginCaptchaImg");
  const baseSrc = img.getAttribute("src");
  document.getElementById("loginCaptchaRefresh").addEventListener("click", function () {
    img.src = `${baseSrc}?t=${Date.now()}`;
    const captchaInput = document.getElementById("loginCaptcha");
    captchaInput.value = "";
    captchaInput.focus();
    updateSubmit();
  });
})();
