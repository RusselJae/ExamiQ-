(function () {
    "use strict";

    var toggle = document.querySelector("[data-notifications-filters-toggle]");
    var panel = document.querySelector("[data-notifications-filters-panel]");
    if (!toggle || !panel) {
        return;
    }

    toggle.addEventListener("click", function () {
        var open = panel.hasAttribute("hidden");
        if (open) {
            panel.removeAttribute("hidden");
        } else {
            panel.setAttribute("hidden", "");
        }
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
})();
