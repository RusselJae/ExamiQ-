/**
 * Coordinator Faculty Courses table: click a faculty row to reveal every
 * course/section assignment for that faculty member.
 */
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        function toggle(row) {
            var targetId = row.getAttribute("data-faculty-toggle");
            var detail = targetId ? document.getElementById(targetId) : null;
            if (!detail) return;
            var open = !detail.classList.contains("hidden");
            detail.classList.toggle("hidden", open);
            row.classList.toggle("is-open", !open);
            row.setAttribute("aria-expanded", open ? "false" : "true");
        }

        document.querySelectorAll("tr[data-faculty-toggle]").forEach(function (row) {
            row.addEventListener("click", function (event) {
                if (event.target.closest("a, button, details, summary, form")) return;
                toggle(row);
            });
            row.addEventListener("keydown", function (event) {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    toggle(row);
                }
            });
        });
    });
})();
