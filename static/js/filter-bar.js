(function () {
    "use strict";

    function initFilterBar(root) {
        var form = root.querySelector("[data-filter-bar]");
        if (!form || form.dataset.filterBarReady === "1") {
            return;
        }
        form.dataset.filterBarReady = "1";

        var toggle = form.querySelector("[data-filter-toggle]");
        if (toggle) {
            toggle.addEventListener("click", function () {
                var open = form.classList.toggle("is-filters-open");
                toggle.setAttribute("aria-expanded", open ? "true" : "false");
            });
        }

        root.querySelectorAll("[data-filter-chip]").forEach(function (chip) {
            chip.addEventListener("click", function () {
                var name = chip.getAttribute("data-filter-chip");
                if (!name) {
                    return;
                }
                var url = new URL(window.location.href);
                url.searchParams.delete(name);
                window.location.assign(url.toString());
            });
        });
    }

    function initAll() {
        document.querySelectorAll(".filter-bar-container").forEach(initFilterBar);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAll);
    } else {
        initAll();
    }
})();
