/**
 * Client-side search + type filters for learning materials libraries.
 */
(function () {
    "use strict";

    function initLibrary(root) {
        var search = root.querySelector("[data-library-search]");
        var items = Array.prototype.slice.call(root.querySelectorAll("[data-library-item]"));
        var emptyFilter = root.querySelector("[data-library-empty-filter]");
        var countEl = root.querySelector("[data-library-count]");
        var chips = Array.prototype.slice.call(root.querySelectorAll("[data-library-filter]"));
        var activeType = "";

        function apply() {
            var q = (search && search.value || "").trim().toLowerCase();
            var visible = 0;
            items.forEach(function (item) {
                var title = item.getAttribute("data-title") || "";
                var type = item.getAttribute("data-type") || "";
                var matchQ = !q || title.indexOf(q) !== -1;
                var matchT = !activeType || type === activeType;
                var show = matchQ && matchT;
                item.classList.toggle("hidden", !show);
                if (show) visible += 1;
            });
            if (emptyFilter) emptyFilter.classList.toggle("hidden", visible > 0 || !items.length);
            if (countEl) {
                countEl.textContent = visible + (visible === 1 ? " item" : " items");
            }
        }

        chips.forEach(function (chip) {
            chip.addEventListener("click", function () {
                activeType = chip.getAttribute("data-library-filter") || "";
                chips.forEach(function (other) {
                    other.classList.toggle("is-active", other === chip);
                });
                apply();
            });
        });

        if (search) search.addEventListener("input", apply);
        apply();
    }

    function initFileName() {
        var input = document.getElementById("material-file");
        var label = document.querySelector("[data-file-name]");
        var nameInput = document.querySelector("[data-original-name]");
        if (!input) return;
        input.addEventListener("change", function () {
            var fileName = input.files && input.files[0] ? input.files[0].name : "";
            if (label) {
                label.textContent = fileName || "No file chosen";
            }
            if (nameInput && fileName) {
                if (!nameInput.value.trim() || nameInput.dataset.autoFilled === "1") {
                    nameInput.value = fileName;
                    nameInput.dataset.autoFilled = "1";
                }
            }
        });
        if (nameInput) {
            nameInput.addEventListener("input", function () {
                nameInput.dataset.autoFilled = "0";
            });
        }
    }

    function init() {
        document.querySelectorAll("[data-materials-library]").forEach(initLibrary);
        initFileName();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
