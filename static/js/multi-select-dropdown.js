/**
 * Multi-select dropdown: "N Selected" + checkboxes + selected title chips.
 * Bind via data-multi-select on a wrapper containing a <select multiple>.
 * Add data-select-all to include a "Select all" toggle row.
 * Add data-search to include a filter input at the top of the menu.
 */
(function () {
    function optionLabel(opt) {
        return (opt.textContent || opt.label || "").trim();
    }

    function optionRows(menu) {
        return Array.prototype.slice.call(
            menu.querySelectorAll("[data-option-value]")
        );
    }

    function lockedValues(root) {
        var raw = (root && root.getAttribute("data-locked-values")) || "";
        return raw
            .split(",")
            .map(function (value) {
                return value.trim();
            })
            .filter(Boolean);
    }

    function isLockedValue(root, value) {
        return lockedValues(root).indexOf(value) !== -1;
    }

    function ensureLockedSelected(root, select) {
        lockedValues(root).forEach(function (value) {
            var opt = Array.from(select.options).find(function (option) {
                return option.value === value;
            });
            if (opt) {
                opt.selected = true;
            }
        });
    }

    function appendDefaultBadge(root, row, value) {
        if (!isLockedValue(root, value)) return;
        var badge = document.createElement("span");
        badge.className = "multi-select-default-badge";
        badge.textContent = root.getAttribute("data-locked-badge") || "default";
        row.appendChild(badge);
    }

    function syncFromSelect(root, select, triggerLabel, menu, chips, selectAllCb, chipsWrap) {
        ensureLockedSelected(root, select);
        var selected = Array.from(select.selectedOptions);
        var count = selected.length;
        var totalOptions = Array.from(select.options).filter(function (o) { return o.value; }).length;
        var allSelected = totalOptions > 0 && count === totalOptions;

        var emptyLabel =
            root.getAttribute("data-empty-label") || "Select course subjects";
        if (allSelected && count > 0) {
            triggerLabel.textContent = "All Selected (" + count + ")";
        } else {
            triggerLabel.textContent =
                count === 0 ? emptyLabel : count + " Selected";
        }

        optionRows(menu).forEach(function (row) {
            var value = row.getAttribute("data-option-value");
            var cb = row.querySelector('input[type="checkbox"]');
            if (cb) {
                cb.checked = Array.from(select.options).some(function (o) {
                    return o.value === value && o.selected;
                });
            }
        });

        if (selectAllCb) {
            selectAllCb.checked = allSelected;
        }

        if (!chips) return;
        chips.innerHTML = "";
        selected.forEach(function (opt) {
            var chip = document.createElement("span");
            chip.className = "multi-select-chip";
            if (isLockedValue(root, opt.value)) {
                chip.classList.add("multi-select-chip--locked");
            }
            var label = document.createElement("span");
            label.textContent = optionLabel(opt);
            chip.appendChild(label);
            if (isLockedValue(root, opt.value)) {
                var badge = document.createElement("span");
                badge.className = "multi-select-default-badge";
                badge.textContent = root.getAttribute("data-locked-badge") || "default";
                chip.appendChild(badge);
            } else {
                var remove = document.createElement("button");
                remove.type = "button";
                remove.className = "multi-select-chip__remove";
                remove.setAttribute("aria-label", "Remove " + optionLabel(opt));
                remove.textContent = "×";
                remove.addEventListener("click", function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    opt.selected = false;
                    select.dispatchEvent(new Event("change", { bubbles: true }));
                    syncFromSelect(
                        root,
                        select,
                        triggerLabel,
                        menu,
                        chips,
                        selectAllCb,
                        chipsWrap
                    );
                });
                chip.appendChild(remove);
            }
            chips.appendChild(chip);
        });
        chips.classList.toggle("hidden", selected.length === 0);
        if (chipsWrap) {
            chipsWrap.classList.toggle("hidden", selected.length === 0);
            chipsWrap.setAttribute("aria-hidden", selected.length === 0 ? "true" : "false");
        }
    }

    function filterOptions(menu, query) {
        var q = String(query || "").trim().toLowerCase();
        var shown = 0;
        optionRows(menu).forEach(function (row) {
            if (row.classList.contains("multi-select-empty")) return;
            var text = (row.textContent || "").trim().toLowerCase();
            var match = !q || text.indexOf(q) !== -1;
            row.classList.toggle("hidden", !match);
            if (match) shown += 1;
        });
        var empty = menu.querySelector(".multi-select-empty");
        if (empty) {
            empty.classList.toggle("hidden", shown > 0);
        }
    }

    function initRoot(root) {
        var select = root.querySelector("select[multiple]");
        if (!select || root.dataset.multiSelectReady === "1") return;
        root.dataset.multiSelectReady = "1";

        select.classList.add("multi-select-native");
        select.setAttribute("tabindex", "-1");
        select.setAttribute("aria-hidden", "true");

        var trigger = document.createElement("button");
        trigger.type = "button";
        trigger.className = "multi-select-trigger";
        trigger.setAttribute("aria-expanded", "false");
        var triggerLabel = document.createElement("span");
        triggerLabel.className = "multi-select-trigger__label";
        var chevron = document.createElement("span");
        chevron.className = "multi-select-trigger__chevron";
        chevron.setAttribute("aria-hidden", "true");
        chevron.innerHTML =
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>';
        trigger.appendChild(triggerLabel);
        trigger.appendChild(chevron);

        var menu = document.createElement("div");
        menu.className = "multi-select-menu hidden";
        menu.setAttribute("role", "listbox");

        var searchInput = null;
        if (root.dataset.search !== undefined) {
            searchInput = document.createElement("input");
            searchInput.type = "search";
            searchInput.className = "multi-select-search";
            searchInput.placeholder =
                root.getAttribute("data-search-placeholder") ||
                "Search…";
            searchInput.setAttribute("autocomplete", "off");
            searchInput.addEventListener("click", function (e) {
                e.stopPropagation();
            });
            searchInput.addEventListener("input", function () {
                filterOptions(menu, searchInput.value);
            });
            menu.appendChild(searchInput);

            var emptyRow = document.createElement("div");
            emptyRow.className = "multi-select-empty hidden";
            emptyRow.textContent = "No matches";
            menu.appendChild(emptyRow);
        }

        var chips = document.createElement("div");
        chips.className = "multi-select-chips hidden";
        chips.setAttribute("aria-live", "polite");

        var selectedTitle = root.getAttribute("data-selected-heading") || "Selected course subjects";
        var chipsWrap = document.createElement("div");
        chipsWrap.className = "multi-select-chips-wrap hidden";
        var chipsHeading = document.createElement("p");
        chipsHeading.className = "multi-select-chips-heading";
        chipsHeading.textContent = selectedTitle;
        chipsWrap.appendChild(chipsHeading);
        chipsWrap.appendChild(chips);

        var selectAllCb = null;
        if (root.dataset.selectAll !== undefined) {
            var selectAllRow = document.createElement("label");
            selectAllRow.className = "multi-select-option multi-select-select-all";
            selectAllCb = document.createElement("input");
            selectAllCb.type = "checkbox";
            var selectAllText = document.createElement("span");
            selectAllText.textContent = "Select all";
            selectAllRow.appendChild(selectAllCb);
            selectAllRow.appendChild(selectAllText);
            menu.appendChild(selectAllRow);

            selectAllCb.addEventListener("change", function () {
                var isChecked = selectAllCb.checked;
                optionRows(menu).forEach(function (row) {
                    if (row.classList.contains("hidden")) return;
                    var value = row.getAttribute("data-option-value");
                    if (!isChecked && isLockedValue(root, value)) return;
                    var opt = Array.from(select.options).find(function (o) {
                        return o.value === value;
                    });
                    if (opt) opt.selected = isChecked || isLockedValue(root, value);
                    var cb = row.querySelector('input[type="checkbox"]');
                    if (cb) cb.checked = opt ? opt.selected : false;
                });
                ensureLockedSelected(root, select);
                select.dispatchEvent(new Event("change", { bubbles: true }));
                syncFromSelect(root, select, triggerLabel, menu, chips, selectAllCb, chipsWrap);
            });
        }

        Array.from(select.options).forEach(function (opt) {
            if (!opt.value) return;
            var row = document.createElement("label");
            row.className = "multi-select-option";
            if (isLockedValue(root, opt.value)) {
                row.classList.add("multi-select-option--locked");
            }
            row.setAttribute("data-option-value", opt.value);
            var cb = document.createElement("input");
            cb.type = "checkbox";
            cb.value = opt.value;
            cb.checked = opt.selected || isLockedValue(root, opt.value);
            if (isLockedValue(root, opt.value)) {
                cb.disabled = true;
                opt.selected = true;
            }
            var text = document.createElement("span");
            text.className = "multi-select-option__label";
            text.textContent = optionLabel(opt);
            row.appendChild(cb);
            row.appendChild(text);
            appendDefaultBadge(root, row, opt.value);
            menu.appendChild(row);

            cb.addEventListener("change", function () {
                if (isLockedValue(root, opt.value)) {
                    cb.checked = true;
                    opt.selected = true;
                    return;
                }
                opt.selected = cb.checked;
                ensureLockedSelected(root, select);
                select.dispatchEvent(new Event("change", { bubbles: true }));
                syncFromSelect(root, select, triggerLabel, menu, chips, selectAllCb, chipsWrap);
            });
        });

        root.appendChild(trigger);
        root.appendChild(menu);
        root.appendChild(chipsWrap);

        function closeMenu() {
            menu.classList.add("hidden");
            trigger.setAttribute("aria-expanded", "false");
            root.classList.remove("multi-select--open");
        }

        function openMenu() {
            menu.classList.remove("hidden");
            trigger.setAttribute("aria-expanded", "true");
            root.classList.add("multi-select--open");
            if (searchInput) {
                searchInput.value = "";
                filterOptions(menu, "");
                searchInput.focus();
            }
        }

        trigger.addEventListener("click", function (e) {
            e.preventDefault();
            if (menu.classList.contains("hidden")) openMenu();
            else closeMenu();
        });

        document.addEventListener("click", function (e) {
            if (!root.contains(e.target)) closeMenu();
        });

        syncFromSelect(root, select, triggerLabel, menu, chips, selectAllCb, chipsWrap);
    }

    function initAll(scope) {
        (scope || document).querySelectorAll("[data-multi-select]").forEach(initRoot);
    }

    document.addEventListener("DOMContentLoaded", function () {
        initAll(document);
    });

    window.ExamiQMultiSelect = { init: initAll };
})();
