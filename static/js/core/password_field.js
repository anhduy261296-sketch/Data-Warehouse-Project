// Mọi ô type="password" có sẵn trên trang tự có nút mắt để xem nội dung đang nhập.
(function () {
  function setShown(field, shown) {
    const button = field.querySelector("button");
    const label = shown ? "Ẩn mật khẩu" : "Hiện mật khẩu";
    field.querySelector("input").type = shown ? "text" : "password";
    button.title = label;
    button.setAttribute("aria-label", label);
    button.querySelector("i").className = shown ? "fas fa-eye-slash" : "fas fa-eye";
  }

  function hideAll(root) {
    root.querySelectorAll(".password-field").forEach((field) => setShown(field, false));
  }

  document.querySelectorAll('input[type="password"]').forEach((input) => {
    const wasFocused = document.activeElement === input;
    const field = document.createElement("div");
    field.className = "password-field";
    input.before(field);
    field.append(input);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "password-field-toggle";
    button.tabIndex = -1; // Tab đi thẳng sang ô tiếp theo, nút mắt chỉ dùng bằng chuột.
    button.innerHTML = "<i></i>";
    button.addEventListener("click", () => {
      setShown(field, input.type === "password");
      input.focus();
    });
    field.append(button);
    setShown(field, false);
    if (wasFocused) input.focus();
  });

  // Trả về dạng ẩn trước khi gửi form để trình duyệt không lưu mật khẩu vào lịch sử ô nhập.
  document.addEventListener("submit", (event) => hideAll(event.target), true);
  if (window.jQuery) window.jQuery(document).on("hidden.bs.modal", ".modal", (event) => hideAll(event.target));
})();
