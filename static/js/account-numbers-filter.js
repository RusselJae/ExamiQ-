/**
 * Coordinator accounts — client-side filter for the "Student numbers" tab.
 * Matches the digits typed against each row's student number (and type).
 */
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var input = document.getElementById("roster-search");
        var table = document.getElementById("roster-table");
        if (!input || !table) return;

        var rows = Array.prototype.slice.call(
            table.querySelectorAll("tbody tr[data-roster-number]")
        );
        var empty = document.getElementById("roster-empty-filter");

        function apply() {
            var q = (input.value || "").trim().toLowerCase();
            var visible = 0;
            rows.forEach(function (row) {
                var text =
                    (row.getAttribute("data-roster-number") || "") +
                    " " +
                    (row.getAttribute("data-roster-type") || "");
                var show = !q || text.toLowerCase().indexOf(q) !== -1;
                row.style.display = show ? "" : "none";
                if (show) visible += 1;
            });
            if (empty) empty.classList.toggle("hidden", visible > 0 || !rows.length);
        }

        input.addEventListener("input", apply);
    });
})();
