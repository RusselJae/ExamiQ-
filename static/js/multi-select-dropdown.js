/**
 * Multi-select dropdown: "N Selected" + checkboxes + selected title chips.
 * Bind via data-multi-select on a wrapper containing a <select multiple>.
 * Add data-select-all to include a "Select all" toggle row.
 */
(function () {
    function optionLabel(opt) {
        return (opt.textContent || opt.label || "").trim();
    }

    function syncFromSelect(root, select, triggerLabel, menu, chips, selectAllCb, chipsWrap) {
        var selected = Array.from(select.selectedOptions);
        var count = selected.length;
        var totalOptions = Array.from(select.options).filter(function (o) { return o.value; }).length;
        var allSelected = totalOptions > 0 && count === totalOptions;

        if (allSelected && count > 0) {
            triggerLabel.textContent = "All Selected (" + count + ")";
        } else {
            triggerLabel.textContent =
                count === 0 ? "Select course subjects" : count + " Selected";
        }

        menu.querySelectorAll("[data-option-value]").forEach(function (row) {
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
            chip.textContent = optionLabel(opt);
            chips.appendChild(chip);
        });
        chips.classList.toggle("hidden", selected.length === 0);
        if (chipsWrap) {
            chipsWrap.classList.toggle("hidden", selected.length === 0);
            chipsWrap.setAttribute("aria-hidden", selected.length === 0 ? "true" : "false");
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
                Array.from(select.options).forEach(function (opt) {
                    if (!opt.value) return;
                    opt.selected = isChecked;
                });
                Array.from(menu.querySelectorAll('[data-option-value] input[type="checkbox"]')).forEach(function (cb) {
                    cb.checked = isChecked;
                });
                select.dispatchEvent(new Event("change", { bubbles: true }));
                syncFromSelect(root, select, triggerLabel, menu, chips, selectAllCb, chipsWrap);
            });
        }

        Array.from(select.options).forEach(function (opt) {
            if (!opt.value) return;
            var row = document.createElement("label");
            row.className = "multi-select-option";
            row.setAttribute("data-option-value", opt.value);
            var cb = document.createElement("input");
            cb.type = "checkbox";
            cb.value = opt.value;
            cb.checked = opt.selected;
            var text = document.createElement("span");
            text.textContent = optionLabel(opt);
            row.appendChild(cb);
            row.appendChild(text);
            menu.appendChild(row);

            cb.addEventListener("change", function () {
                opt.selected = cb.checked;
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
