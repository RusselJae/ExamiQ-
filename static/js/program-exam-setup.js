(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var search = document.getElementById("subject-timer-search");
        var rows = Array.prototype.slice.call(
            document.querySelectorAll(".subject-timer-row")
        );
        var empty = document.getElementById("subject-timer-empty-filter");
        var selectAll = document.getElementById("subject-timer-select-all");
        var defaultInput = document.getElementById("default_seconds");

        function applyFilter() {
            var q = (search && search.value || "").trim().toLowerCase();
            var visible = 0;
            rows.forEach(function (row) {
                var match =
                    !q ||
                    (row.dataset.code || "").indexOf(q) >= 0 ||
                    (row.dataset.name || "").indexOf(q) >= 0;
                row.classList.toggle("hidden", !match);
                if (match) visible += 1;
            });
            if (empty) empty.classList.toggle("hidden", visible > 0);
        }

        if (search) search.addEventListener("input", applyFilter);

        if (selectAll) {
            selectAll.addEventListener("change", function () {
                var checked = selectAll.checked;
                rows.forEach(function (row) {
                    if (row.classList.contains("hidden")) return;
                    var cb = row.querySelector(".subject-timer-check");
                    if (cb) cb.checked = checked;
                });
            });
        }

        if (defaultInput) {
            defaultInput.addEventListener("input", function () {
                var value = parseInt(defaultInput.value, 10);
                if (isNaN(value)) return;
                rows.forEach(function (row) {
                    var cb = row.querySelector(".subject-timer-check");
                    if (!cb || !cb.checked) return;
                    var input = row.querySelector(".subject-timer-input");
                    if (input) input.value = String(value);
                });
            });
        }
    });
})();
