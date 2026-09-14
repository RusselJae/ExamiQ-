/**
 * Start Exam setup UI: extra subjects, pills, and live summary estimates.
 */
(function () {
    "use strict";

    function parseIntAttr(el, name, fallback) {
        var n = parseInt(el && el.getAttribute(name), 10);
        return isNaN(n) ? fallback : n;
    }

    function getExtraPanelControls() {
        return {
            btn: document.getElementById("toggle-extra-subjects-btn"),
            panel: document.getElementById("extra-subjects-panel"),
        };
    }

    function setExtraPanelOpen(open) {
        var controls = getExtraPanelControls();
        var btn = controls.btn;
        var panel = controls.panel;
        if (!btn || !panel) return;

        if (open) {
            panel.removeAttribute("hidden");
            panel.classList.remove("hidden");
            btn.setAttribute("aria-expanded", "true");
            btn.innerHTML = "<span aria-hidden=\"true\">−</span> Hide other-year subjects";
        } else {
            panel.setAttribute("hidden", "");
            panel.classList.add("hidden");
            btn.setAttribute("aria-expanded", "false");
            btn.innerHTML = "<span aria-hidden=\"true\">+</span> Add subjects from other years";
        }
    }

    function isExtraPanelOpen() {
        var panel = getExtraPanelControls().panel;
        if (!panel) return false;
        return !panel.hasAttribute("hidden") && !panel.classList.contains("hidden");
    }

    function initExtraToggle() {
        var btn = getExtraPanelControls().btn;
        var panel = getExtraPanelControls().panel;
        if (!btn || !panel) return;

        setExtraPanelOpen(isExtraPanelOpen());
        btn.addEventListener("click", function () {
            setExtraPanelOpen(!isExtraPanelOpen());
        });
    }

    function initExtraCards() {
        document.querySelectorAll("[data-extra-subject]").forEach(function (input) {
            var card = input.closest(".exam-subject-card");
            if (!card) return;
            function sync() {
                card.classList.toggle("is-selected", input.checked);
                updateSummary();
            }
            input.addEventListener("change", sync);
            sync();
        });
    }

    function initSelectAllExtras() {
        document.querySelectorAll("[data-select-all-extras]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                setExtraPanelOpen(true);
                document.querySelectorAll("[data-extra-subject]").forEach(function (input) {
                    if (!input.checked) {
                        input.checked = true;
                        input.dispatchEvent(new Event("change", { bubbles: true }));
                    } else {
                        var card = input.closest(".exam-subject-card");
                        if (card) card.classList.add("is-selected");
                    }
                });
                updateSummary();
            });
        });
    }

    function syncSelectFromPills(group, select) {
        var multiple = group.hasAttribute("data-pill-multiple");
        var locked = (group.getAttribute("data-locked-values") || "")
            .split(",")
            .map(function (v) { return v.trim(); })
            .filter(Boolean);

        if (multiple) {
            var selected = [];
            group.querySelectorAll("[data-pill-value].is-selected").forEach(function (btn) {
                selected.push(btn.getAttribute("data-pill-value"));
            });
            locked.forEach(function (value) {
                if (selected.indexOf(value) === -1) selected.unshift(value);
            });
            Array.prototype.forEach.call(select.options, function (opt) {
                opt.selected = selected.indexOf(opt.value) !== -1;
            });
        } else {
            var active = group.querySelector("[data-pill-value].is-selected");
            if (active) select.value = active.getAttribute("data-pill-value") || select.value;
        }
        select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function initPills() {
        document.querySelectorAll("[data-setup-pills]").forEach(function (group) {
            if (group.dataset.bound === "1") return;
            group.dataset.bound = "1";
            var targetId = group.getAttribute("data-pill-target");
            var select = targetId ? document.getElementById(targetId) : null;
            if (!select) return;
            var multiple = group.hasAttribute("data-pill-multiple");
            var locked = (group.getAttribute("data-locked-values") || "")
                .split(",")
                .map(function (v) { return v.trim(); })
                .filter(Boolean);

            group.querySelectorAll("[data-pill-value]").forEach(function (btn) {
                btn.addEventListener("click", function () {
                    var value = btn.getAttribute("data-pill-value") || "";
                    if (locked.indexOf(value) !== -1) return;

                    if (multiple) {
                        btn.classList.toggle("is-selected");
                        btn.setAttribute(
                            "aria-pressed",
                            btn.classList.contains("is-selected") ? "true" : "false"
                        );
                    } else {
                        group.querySelectorAll("[data-pill-value]").forEach(function (other) {
                            var on = other === btn;
                            other.classList.toggle("is-selected", on);
                            other.setAttribute("aria-pressed", on ? "true" : "false");
                        });
                    }
                    syncSelectFromPills(group, select);
                });
            });
            syncSelectFromPills(group, select);
        });
    }

    function updateSummary() {
        var form = document.getElementById("review-setup-form");
        if (!form) return;
        var yearCount = parseIntAttr(form, "data-year-count", 0);
        var minQ = parseIntAttr(form, "data-min-questions", 3);
        var seconds = parseIntAttr(form, "data-seconds", 30);
        var maxQ = parseIntAttr(form, "data-max-questions", 100);
        var extraCount = form.querySelectorAll("[data-extra-subject]:checked").length;
        var subjects = yearCount + extraCount;
        var questions = Math.min(maxQ, Math.max(subjects, 1) * minQ);
        var minutes = Math.max(1, Math.ceil((questions * seconds) / 60));

        var countEl = form.querySelector("[data-selected-count]");
        var subjectsEl = form.querySelector("[data-summary-subjects]");
        var questionsEl = form.querySelector("[data-summary-questions]");
        var minutesEl = form.querySelector("[data-summary-minutes]");
        if (countEl) countEl.textContent = subjects + " selected";
        if (subjectsEl) subjectsEl.textContent = String(subjects);
        if (questionsEl) questionsEl.textContent = "~" + questions;
        if (minutesEl) minutesEl.textContent = "~" + minutes + " min";
    }

    function init() {
        initExtraToggle();
        initExtraCards();
        initSelectAllExtras();
        initPills();
        updateSummary();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
