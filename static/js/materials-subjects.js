/**
 * Client-side search + year/semester filters for the student materials hub.
 * Rows carry data-code / data-name / data-year / data-semester attributes.
 */
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var search = document.getElementById("materials-subject-search");
        var year = document.getElementById("materials-subject-year");
        var semester = document.getElementById("materials-subject-semester");
        var rows = Array.prototype.slice.call(
            document.querySelectorAll(".materials-subject-row")
        );
        var empty = document.getElementById("materials-subjects-empty-filter");
        if (!rows.length) return;

        function apply() {
            var q = ((search && search.value) || "").trim().toLowerCase();
            var y = (year && year.value) || "";
            var s = (semester && semester.value) || "";
            var visible = 0;
            rows.forEach(function (row) {
                var code = row.getAttribute("data-code") || "";
                var name = row.getAttribute("data-name") || "";
                var matchQ = !q || code.indexOf(q) !== -1 || name.indexOf(q) !== -1;
                var matchY = !y || row.getAttribute("data-year") === y;
                var matchS = !s || row.getAttribute("data-semester") === s;
                var show = matchQ && matchY && matchS;
                row.classList.toggle("hidden", !show);
                if (show) visible += 1;
            });
            if (empty) empty.classList.toggle("hidden", visible > 0);
        }

        if (search) search.addEventListener("input", apply);
        if (year) year.addEventListener("change", apply);
        if (semester) semester.addEventListener("change", apply);

        /* Toolbar chrome: Filter hides/shows the panel; Reset clears the
           search and both dropdowns, then re-applies. */
        var form = search ? search.closest("[data-filter-bar]") : null;
        if (form) {
            var toggle = form.querySelector("[data-filter-toggle]");
            if (toggle) {
                var desktop = window.matchMedia("(min-width: 640px)").matches;
                if (!desktop) {
                    form.classList.add("is-collapsed");
                    toggle.setAttribute("aria-expanded", "false");
                }
                toggle.addEventListener("click", function () {
                    var collapsed = form.classList.toggle("is-collapsed");
                    toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
                });
            }
        }
        var reset = form ? form.querySelector("[data-toolbar-reset]") : null;
        if (reset) {
            reset.addEventListener("click", function () {
                if (search) {
                    search.value = "";
                }
                if (year) year.value = "";
                if (semester) semester.value = "";
                apply();
            });
        }
    });
})();
