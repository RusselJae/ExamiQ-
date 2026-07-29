/**
 * Multi-select dropdown: "N Selected" + checkboxes + selected title chips.
 * Bind via data-multi-select on a wrapper containing a <select multiple>.
 */
(function () {
    function optionLabel(opt) {
        return (opt.textContent || opt.label || "").trim();
    }

    function syncFromSelect(root, select, triggerLabel, menu, chips) {
        const selected = Array.from(select.selectedOptions);
        const count = selected.length;
        triggerLabel.textContent = count === 0 ? "Select courses" : count + " Selected";

        menu.querySelectorAll("[data-option-value]").forEach(function (row) {
            const value = row.getAttribute("data-option-value");
            const cb = row.querySelector('input[type="checkbox"]');
            if (cb) {
                cb.checked = Array.from(select.options).some(function (o) {
                    return o.value === value && o.selected;
                });
            }
        });

        if (!chips) return;
        chips.innerHTML = "";
        selected.forEach(function (opt) {
            const chip = document.createElement("span");
            chip.className = "multi-select-chip";
            chip.textContent = optionLabel(opt);
            chips.appendChild(chip);
        });
        chips.classList.toggle("hidden", selected.length === 0);
    }

    function initRoot(root) {
        const select = root.querySelector("select[multiple]");
        if (!select || root.dataset.multiSelectReady === "1") return;
        root.dataset.multiSelectReady = "1";

        select.classList.add("multi-select-native");
        select.setAttribute("tabindex", "-1");
        select.setAttribute("aria-hidden", "true");

        const trigger = document.createElement("button");
        trigger.type = "button";
        trigger.className = "multi-select-trigger";
        trigger.setAttribute("aria-expanded", "false");
        const triggerLabel = document.createElement("span");
        triggerLabel.className = "multi-select-trigger__label";
        const chevron = document.createElement("span");
        chevron.className = "multi-select-trigger__chevron";
        chevron.setAttribute("aria-hidden", "true");
        chevron.innerHTML =
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>';
        trigger.appendChild(triggerLabel);
        trigger.appendChild(chevron);

        const menu = document.createElement("div");
        menu.className = "multi-select-menu hidden";
        menu.setAttribute("role", "listbox");

        Array.from(select.options).forEach(function (opt) {
            if (!opt.value) return;
            const row = document.createElement("label");
            row.className = "multi-select-option";
            row.setAttribute("data-option-value", opt.value);
            const cb = document.createElement("input");
            cb.type = "checkbox";
            cb.value = opt.value;
            cb.checked = opt.selected;
            const text = document.createElement("span");
            text.textContent = optionLabel(opt);
            row.appendChild(cb);
            row.appendChild(text);
            menu.appendChild(row);

            cb.addEventListener("change", function () {
                opt.selected = cb.checked;
                select.dispatchEvent(new Event("change", { bubbles: true }));
                syncFromSelect(root, select, triggerLabel, menu, chips);
            });
        });

        const chips = document.createElement("div");
        chips.className = "multi-select-chips hidden";
        chips.setAttribute("aria-live", "polite");

        const selectedTitle = root.getAttribute("data-selected-heading") || "Selected courses";
        const chipsWrap = document.createElement("div");
        chipsWrap.className = "multi-select-chips-wrap";
        const chipsHeading = document.createElement("p");
        chipsHeading.className = "multi-select-chips-heading";
        chipsHeading.textContent = selectedTitle;
        chipsWrap.appendChild(chipsHeading);
        chipsWrap.appendChild(chips);

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

        syncFromSelect(root, select, triggerLabel, menu, chips);
    }

    function initAll(scope) {
        (scope || document).querySelectorAll("[data-multi-select]").forEach(initRoot);
    }

    document.addEventListener("DOMContentLoaded", function () {
        initAll(document);
    });

    window.ExamiQMultiSelect = { init: initAll };
})();
