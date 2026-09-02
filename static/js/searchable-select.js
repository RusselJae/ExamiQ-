/**
 * Lightweight searchable select (combobox) for faculty filters.
 * Markup: .searchable-select[data-searchable-select] with trigger, panel, options.
 */
(function () {
    "use strict";

    function initOne(root) {
        if (!root || root.dataset.bound === "1") return;
        root.dataset.bound = "1";

        const trigger = root.querySelector(".searchable-select__trigger");
        const valueEl = root.querySelector(".searchable-select__value");
        const panel = root.querySelector(".searchable-select__panel");
        const search = root.querySelector(".searchable-select__search");
        const list = root.querySelector(".searchable-select__list");
        const hidden = root.querySelector('input[type="hidden"]');
        if (!trigger || !panel || !list || !hidden) return;

        const options = Array.prototype.slice.call(
            list.querySelectorAll(".searchable-select__option[data-value]")
        );
        let activeIndex = -1;

        function setOpen(open) {
            root.classList.toggle("is-open", open);
            panel.classList.toggle("hidden", !open);
            trigger.setAttribute("aria-expanded", open ? "true" : "false");
            if (open && search) {
                search.value = "";
                filterOptions("");
                search.focus();
            }
        }

        function visibleOptions() {
            return options.filter(function (opt) {
                return !opt.classList.contains("hidden") && !opt.classList.contains("is-empty");
            });
        }

        function setActive(index) {
            const vis = visibleOptions();
            activeIndex = index;
            options.forEach(function (opt) {
                opt.classList.remove("is-active");
            });
            if (activeIndex >= 0 && activeIndex < vis.length) {
                vis[activeIndex].classList.add("is-active");
                vis[activeIndex].scrollIntoView({ block: "nearest" });
            }
        }

        function filterOptions(query) {
            const q = String(query || "").trim().toLowerCase();
            let shown = 0;
            options.forEach(function (opt) {
                if (opt.classList.contains("is-empty")) return;
                const hay = (opt.dataset.search || opt.textContent || "").toLowerCase();
                const match = !q || hay.indexOf(q) !== -1;
                opt.classList.toggle("hidden", !match);
                if (match) shown += 1;
            });
            let empty = list.querySelector(".searchable-select__option.is-empty");
            if (!empty) {
                empty = document.createElement("li");
                empty.className = "searchable-select__option is-empty";
                empty.textContent = "No matches";
                list.appendChild(empty);
            }
            empty.classList.toggle("hidden", shown > 0);
            setActive(shown ? 0 : -1);
        }

        function selectOption(opt) {
            if (!opt || opt.classList.contains("is-empty")) return;
            const value = opt.dataset.value || "";
            const label = opt.dataset.label || opt.textContent.trim();
            hidden.value = value;
            if (valueEl) {
                valueEl.textContent = label;
                valueEl.classList.toggle("is-placeholder", !value);
            }
            options.forEach(function (o) {
                o.classList.toggle("is-selected", o === opt);
            });
            setOpen(false);
            hidden.dispatchEvent(new Event("change", { bubbles: true }));

            const navigateTemplate = root.dataset.navigateUrl;
            if (navigateTemplate) {
                if (!value) {
                    window.location = root.dataset.navigateClear || navigateTemplate.replace("{id}", "");
                    return;
                }
                window.location = navigateTemplate.replace("{id}", encodeURIComponent(value));
            }
        }

        trigger.addEventListener("click", function (e) {
            e.preventDefault();
            setOpen(panel.classList.contains("hidden"));
        });

        if (search) {
            search.addEventListener("input", function () {
                filterOptions(search.value);
            });
            search.addEventListener("keydown", function (e) {
                const vis = visibleOptions();
                if (e.key === "ArrowDown") {
                    e.preventDefault();
                    setActive(Math.min(activeIndex + 1, vis.length - 1));
                } else if (e.key === "ArrowUp") {
                    e.preventDefault();
                    setActive(Math.max(activeIndex - 1, 0));
                } else if (e.key === "Enter") {
                    e.preventDefault();
                    if (activeIndex >= 0 && vis[activeIndex]) selectOption(vis[activeIndex]);
                } else if (e.key === "Escape") {
                    e.preventDefault();
                    setOpen(false);
                    trigger.focus();
                }
            });
        }

        list.addEventListener("click", function (e) {
            const opt = e.target.closest(".searchable-select__option[data-value]");
            if (opt) selectOption(opt);
        });

        document.addEventListener("click", function (e) {
            if (!root.contains(e.target)) setOpen(false);
        });
    }

    function initAll(scope) {
        (scope || document)
            .querySelectorAll("[data-searchable-select]")
            .forEach(initOne);
    }

    window.ExamiQSearchableSelect = { init: initAll };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            initAll();
        });
    } else {
        initAll();
    }
})();
