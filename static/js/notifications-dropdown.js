(function () {
  function closeAllNavElements() {
    // Close profile dropdowns
    document.querySelectorAll("[data-dropdown].open").forEach(function (dropdown) {
      dropdown.classList.remove("open");
      var menu = dropdown.querySelector("[data-dropdown-menu]");
      var toggle = dropdown.querySelector("[data-dropdown-toggle]");
      if (menu) menu.classList.add("hidden");
      if (toggle) toggle.setAttribute("aria-expanded", "false");
    });

    // Close notifications dropdown
    document.querySelectorAll("[data-notifications-dropdown]").forEach(function (root) {
      var menu = root.querySelector("[data-notifications-menu]");
      var toggle = root.querySelector("[data-notifications-toggle]");
      if (menu) menu.classList.add("hidden");
      if (toggle) toggle.setAttribute("aria-expanded", "false");
    });

    // Close mobile search floating
    var floating = document.getElementById("nav-search-floating");
    var searchToggle = document.querySelector("[data-nav-search-toggle]");
    if (floating && !floating.classList.contains("hidden")) {
      floating.classList.add("hidden");
      if (searchToggle) searchToggle.setAttribute("aria-expanded", "false");
    }

    // Close chat modal
    var chatModal = document.getElementById("examiq-chat-modal");
    if (chatModal && !chatModal.classList.contains("hidden")) {
      chatModal.classList.add("hidden");
      document.documentElement.classList.remove("examiq-chat-open");
    }

    // Close AI tutor modal
    var aiTutorModal = document.getElementById("examiq-ai-tutor-modal");
    if (aiTutorModal && !aiTutorModal.classList.contains("hidden")) {
      aiTutorModal.classList.add("hidden");
      document.documentElement.classList.remove("examiq-ai-tutor-open");
    }
  }

  function removeNotificationBadge(root) {
    var badge = root.querySelector(".notification-badge");
    if (badge) {
      badge.remove();
    }
  }

  document.addEventListener("click", function (event) {
    var root = event.target.closest("[data-notifications-dropdown]");
    var toggle = event.target.closest("[data-notifications-toggle]");

    if (toggle && root) {
      event.preventDefault();
      var menu = root.querySelector("[data-notifications-menu]");
      if (!menu) return;
      var willOpen = menu.classList.contains("hidden");
      if (willOpen) {
        closeAllNavElements();
        removeNotificationBadge(root);
        menu.classList.remove("hidden");
        toggle.setAttribute("aria-expanded", "true");
      } else {
        /* Clicking the bell again closes the panel. */
        menu.classList.add("hidden");
        toggle.setAttribute("aria-expanded", "false");
        toggle.classList.remove("is-active");
      }
      return;
    }

    if (!root) {
      // Close only notifications dropdown when clicking outside
      document.querySelectorAll("[data-notifications-dropdown]").forEach(function (root) {
        var menu = root.querySelector("[data-notifications-menu]");
        var toggle = root.querySelector("[data-notifications-toggle]");
        if (menu) menu.classList.add("hidden");
        if (toggle) toggle.setAttribute("aria-expanded", "false");
      });
    }
  });

  /* Keep the bell icon black while its dropdown is open. */
  document.addEventListener("click", function (event) {
    var root = event.target.closest("[data-notifications-dropdown]");
    document.querySelectorAll("[data-notifications-dropdown]").forEach(function (item) {
      var toggle = item.querySelector("[data-notifications-toggle]");
      var menu = item.querySelector("[data-notifications-menu]");
      var isOpen = menu && !menu.classList.contains("hidden");
      if (toggle) toggle.classList.toggle("is-active", !!isOpen);
    });
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeAllNavElements();
    }
  });
})();
