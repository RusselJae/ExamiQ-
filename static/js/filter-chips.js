/**
 * Auto-applying filter chips: any change inside a [data-auto-filter-form]
 * submits the form immediately (no Apply button).
 */
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-auto-filter-form]").forEach(function (form) {
            if (form.dataset.bound) return;
            form.dataset.bound = "1";
            var timer = null;
            form.querySelectorAll("input, select").forEach(function (el) {
                el.addEventListener("change", function () {
                    form.submit();
                });
                if (el.type === "search") {
                    el.addEventListener("input", function () {
                        if (timer) window.clearTimeout(timer);
                        timer = window.setTimeout(function () {
                            form.submit();
                        }, 600);
                    });
                }
            });
        });
    });
})();
