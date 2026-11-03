/**
 * Client-side search + status/year filters for the Concepts review list.
 * Cards carry data-code / data-name / data-status / data-year attributes.
 */
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var bar = document.querySelector("[data-concept-filter-bar]");
        if (!bar) return;
        var search = document.getElementById("concept-card-search");
        var status = document.getElementById("concept-card-status");
        var year = document.getElementById("concept-card-year");
        var cards = Array.prototype.slice.call(
            document.querySelectorAll(".concept-card")
        );
        var empty = document.getElementById("concept-cards-empty-filter");
        if (!cards.length) return;

        /* Year options come from the rendered cards (keeps the list to
           years the student actually has concepts in). */
        if (year) {
            var seen = {};
            cards.forEach(function (card) {
                var id = card.getAttribute("data-year") || "";
                var name = card.getAttribute("data-year-name") || "";
                if (id && !seen[id]) {
                    seen[id] = true;
                    var opt = document.createElement("option");
                    opt.value = id;
                    opt.textContent = name || id;
                    year.appendChild(opt);
                }
            });
        }

        function apply() {
            var q = ((search && search.value) || "").trim().toLowerCase();
            var s = (status && status.value) || "";
            var y = (year && year.value) || "";
            var visible = 0;
            cards.forEach(function (card) {
                var code = card.getAttribute("data-code") || "";
                var name = card.getAttribute("data-name") || "";
                var matchQ = !q || code.indexOf(q) !== -1 || name.indexOf(q) !== -1;
                var matchS = !s || card.getAttribute("data-status") === s;
                var matchY = !y || card.getAttribute("data-year") === y;
                var show = matchQ && matchS && matchY;
                card.classList.toggle("hidden", !show);
                if (show) visible += 1;
            });
            if (empty) empty.classList.toggle("hidden", visible > 0);
        }

        if (search) search.addEventListener("input", apply);
        if (status) status.addEventListener("change", apply);
        if (year) year.addEventListener("change", apply);
        apply();
    });
})();
