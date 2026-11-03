(function () {
    "use strict";

    function closeOutsidePickers(event) {
        document.querySelectorAll(".filter-bar__picker[open], .account-kebab[open]").forEach(function (picker) {
            if (!picker.contains(event.target)) {
                picker.removeAttribute("open");
            }
        });
    }

    function initFilterBar(root) {
        var form = root.querySelector("[data-filter-bar]");
        if (!form) {
            return;
        }

        root.querySelectorAll("[data-filter-chip]").forEach(function (chip) {
            if (chip.dataset.bound) return;
            chip.dataset.bound = "1";
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

    function bindDismiss() {
        if (document.filterBarDismissBound) return;
        document.filterBarDismissBound = true;
        /* Filter opens natively via <details>; dismiss it on outside click or
           Escape like a real popover. */
        document.addEventListener("click", closeOutsidePickers);
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                document
                    .querySelectorAll(".filter-bar__picker[open]")
                    .forEach(function (picker) {
                        picker.removeAttribute("open");
                    });
            }
        });
    }

    function initAll() {
        bindDismiss();
        document.querySelectorAll("[data-filter-bar]").forEach(initFilterBar);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAll);
    } else {
        initAll();
    }
})();
