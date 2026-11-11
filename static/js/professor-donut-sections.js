/**
 * Professor dashboard: narrow the section filter to the sections handled for
 * the currently selected course. The donut itself re-renders through
 * donut-filters.js (the section select is a normal filter control).
 */
(function () {
    "use strict";

    function readJson(id) {
        var el = document.getElementById(id);
        if (!el) return {};
        try {
            return JSON.parse(el.textContent) || {};
        } catch (e) {
            return {};
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        var courseSelect = document.getElementById("donut-subject-picker");
        var sectionSelect = document.getElementById("donut-section-picker");
        if (!courseSelect || !sectionSelect) return;

        var sectionMap = readJson("donut-section-map");
        var allSections = readJson("donut-all-sections") || [];
        var allOptions = [{ value: "", label: "All sections" }].concat(
            allSections.map(function (row) {
                return { value: String(row.pk), label: row.label };
            })
        );

        function optionsFor(subjectId) {
            if (!subjectId) return allOptions;
            var rows = sectionMap[String(subjectId)] || [];
            return [{ value: "", label: "All sections" }].concat(
                rows.map(function (row) {
                    return { value: String(row.pk), label: row.label };
                })
            );
        }

        function rebuild() {
            var subjectId = courseSelect.value || "";
            var wanted = optionsFor(subjectId);
            var previous = sectionSelect.value;
            sectionSelect.innerHTML = "";
            wanted.forEach(function (opt) {
                var option = document.createElement("option");
                option.value = opt.value;
                option.textContent = opt.label;
                sectionSelect.appendChild(option);
            });
            var stillValid = wanted.some(function (opt) {
                return opt.value === previous;
            });
            sectionSelect.value = stillValid ? previous : "";
            sectionSelect.disabled = wanted.length <= 1;
        }

        /* Capture so the section list is rebuilt before donut-filters reads
           the controls for its fetch. */
        courseSelect.addEventListener("change", rebuild, true);
        rebuild();
    });
})();
