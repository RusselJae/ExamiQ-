/**
 * Lightweight searchable select (combobox) for faculty filters.
 * Markup: .searchable-select[data-searchable-select] with trigger, panel, options.
 */
(function () {
    "use strict";

    /**
     * Options are read from the DOM on every access so callers can add or
     * remove entries (pending uploads, freshly saved material) after the
     * widget has been bound.
     */
    function optionNodes(root) {
        const list = root && root.querySelector(".searchable-select__list");
        if (!list) return [];
        return Array.prototype.slice.call(
            list.querySelectorAll(".searchable-select__option[data-value]")
        );
    }

    /**
     * Group headings ("Saved material", "New uploads") hide themselves when
     * every option they belong to has been filtered out.
     */
    function updateGroupLabels(root) {
        const list = root && root.querySelector(".searchable-select__list");
        if (!list) return;
        list.querySelectorAll(".searchable-select__group-label").forEach(function (label) {
            const group = label.getAttribute("data-group");
            if (!group) return;
            const visible = list.querySelectorAll(
                '.searchable-select__option[data-group="' + group + '"]:not(.hidden)'
            ).length;
            label.classList.toggle("hidden", visible === 0);
        });
    }

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
            return optionNodes(root).filter(function (opt) {
                return !opt.classList.contains("hidden") && !opt.classList.contains("is-empty");
            });
        }

        function setActive(index) {
            const vis = visibleOptions();
            activeIndex = index;
            optionNodes(root).forEach(function (opt) {
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
            optionNodes(root).forEach(function (opt) {
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
            updateGroupLabels(root);
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
            optionNodes(root).forEach(function (o) {
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

    /**
     * Set the widget's value from code (e.g. after an upload was promoted to
     * a saved module). The label falls back to the matching option's label and
     * then to the root's `data-placeholder` for an empty value.
     */
    function setValue(root, value, label) {
        if (!root) return;
        const hidden = root.querySelector('input[type="hidden"]');
        const valueEl = root.querySelector(".searchable-select__value");
        const next = value == null ? "" : String(value);

        let text = label;
        if (text == null) {
            const match = optionNodes(root).filter(function (opt) {
                return String(opt.dataset.value || "") === next;
            })[0];
            text = match ? match.dataset.label || match.textContent.trim() : "";
        }

        if (hidden) hidden.value = next;
        if (valueEl) {
            const placeholder = root.dataset.placeholder || "";
            valueEl.textContent = next ? text : placeholder;
            valueEl.classList.toggle("is-placeholder", !next);
        }
        optionNodes(root).forEach(function (opt) {
            opt.classList.toggle("is-selected", String(opt.dataset.value || "") === next);
        });
        updateGroupLabels(root);
    }

    function initAll(scope) {
        (scope || document)
            .querySelectorAll("[data-searchable-select]")
            .forEach(initOne);
    }

    window.ExamiQSearchableSelect = { init: initAll, setValue: setValue };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            initAll();
        });
    } else {
        initAll();
    }
})();
