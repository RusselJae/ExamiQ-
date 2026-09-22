(function () {
  function closeAll(exceptEl) {
    document.querySelectorAll("[data-notifications-dropdown]").forEach(function (root) {
      if (exceptEl && root === exceptEl) return;
      var menu = root.querySelector("[data-notifications-menu]");
      var toggle = root.querySelector("[data-notifications-toggle]");
      if (menu) menu.classList.add("hidden");
      if (toggle) toggle.setAttribute("aria-expanded", "false");
    });
  }

  document.addEventListener("click", function (event) {
    var root = event.target.closest("[data-notifications-dropdown]");
    var toggle = event.target.closest("[data-notifications-toggle]");

    if (toggle && root) {
      event.preventDefault();
      var menu = root.querySelector("[data-notifications-menu]");
      if (!menu) return;
      var willOpen = menu.classList.contains("hidden");
      closeAll();
      if (willOpen) {
        menu.classList.remove("hidden");
        toggle.setAttribute("aria-expanded", "true");
      }
      return;
    }

    if (!root) {
      closeAll();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeAll();
    }
  });
})();
