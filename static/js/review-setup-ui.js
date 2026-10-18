/**
 * ExamiQ Review Setup UI
 * Handles tab filtering, searching, custom checkboxes, difficulty pills,
 * questions stepper, timer presets, and live summary estimation.
 */
(function () {
    "use strict";

    var currentTab = "year";

    function getForm() {
        return document.getElementById("review-setup-form");
    }

    function selectTab(tab) {
        var tabButtons = document.querySelectorAll("[data-tab]");
        if (!tab) {
            filterRows();
            return;
        }
        if (tab !== currentTab) {
            currentTab = tab;
            tabButtons.forEach(function (b) {
                var active = b.getAttribute("data-tab") === tab;
                b.classList.toggle("is-active", active);
                b.setAttribute("aria-selected", active ? "true" : "false");
            });
        }
        filterRows();
    }

    function initTabs() {
        var tabButtons = document.querySelectorAll("[data-tab]");
        tabButtons.forEach(function (btn) {
            btn.addEventListener("click", function () {
                selectTab(btn.getAttribute("data-tab"));
            });
        });
    }

    function initSearch() {
        var searchInput = document.getElementById("subject-search-input");
        var clearBtn = document.getElementById("subject-search-clear");

        if (searchInput) {
            searchInput.addEventListener("input", function () {
                filterRows();
            });
        }

        if (clearBtn && searchInput) {
            clearBtn.addEventListener("click", function () {
                searchInput.value = "";
                filterRows();
                searchInput.focus();
            });
        }
    }

    function filterRows() {
        var searchInput = document.getElementById("subject-search-input");
        var query = searchInput ? searchInput.value.trim().toLowerCase() : "";
        var rows = document.querySelectorAll("[data-subject-row]");
        var emptyMsg = document.getElementById("no-search-results");
        var visibleCount = 0;

        rows.forEach(function (row) {
            var category = row.getAttribute("data-category");
            var searchTerms = (row.getAttribute("data-search") || "").toLowerCase();

            var matchesTab = false;
            if (currentTab === "all") {
                matchesTab = true;
            } else if (currentTab === "year" && category === "year") {
                matchesTab = true;
            } else if (currentTab === "other" && category === "other") {
                matchesTab = true;
            }

            var matchesSearch = !query || searchTerms.indexOf(query) !== -1;

            if (matchesTab && matchesSearch) {
                row.style.display = "grid";
                visibleCount++;
            } else {
                row.style.display = "none";
            }
        });

        if (emptyMsg) {
            emptyMsg.style.display = visibleCount === 0 ? "block" : "none";
        }

        syncHeaderCheckbox();
    }

    function initRowsAndCheckboxes() {
        var rows = document.querySelectorAll("[data-subject-row]");
        rows.forEach(function (row) {
            var cb = row.querySelector("[data-subject-checkbox]");
            var box = row.querySelector(".exam-checkbox-box");
            if (!cb) return;

            function syncRowUI() {
                row.classList.toggle("is-selected", cb.checked);
                if (box) {
                    box.classList.toggle("is-checked", cb.checked);
                }
            }

            cb.addEventListener("change", function () {
                syncRowUI();
                updateSummary();
                syncHeaderCheckbox();
            });

            row.addEventListener("click", function (e) {
                if (e.target.closest("label") || e.target.closest("input")) return;
                cb.checked = !cb.checked;
                syncRowUI();
                updateSummary();
                syncHeaderCheckbox();
            });

            syncRowUI();
        });
    }

    function initHeaderCheckbox() {
        var headerCb = document.getElementById("header-select-all");
        var headerBox = document.getElementById("header-checkbox-box");
        if (!headerCb) return;

        headerCb.addEventListener("change", function () {
            var shouldCheck = headerCb.checked;
            var visibleRows = document.querySelectorAll("[data-subject-row]");

            visibleRows.forEach(function (row) {
                if (row.style.display === "none") return;
                var cb = row.querySelector("[data-subject-checkbox]");
                var box = row.querySelector(".exam-checkbox-box");
                if (cb) {
                    cb.checked = shouldCheck;
                    row.classList.toggle("is-selected", shouldCheck);
                    if (box) box.classList.toggle("is-checked", shouldCheck);
                }
            });

            if (headerBox) {
                headerBox.classList.toggle("is-checked", shouldCheck);
            }

            updateSummary();
        });
    }

    function syncHeaderCheckbox() {
        var headerCb = document.getElementById("header-select-all");
        var headerBox = document.getElementById("header-checkbox-box");
        if (!headerCb) return;

        var visibleRows = Array.from(document.querySelectorAll("[data-subject-row]")).filter(function (r) {
            return r.style.display !== "none";
        });

        if (visibleRows.length === 0) {
            headerCb.checked = false;
            if (headerBox) headerBox.classList.remove("is-checked");
            return;
        }

        var allChecked = visibleRows.every(function (r) {
            var cb = r.querySelector("[data-subject-checkbox]");
            return cb && cb.checked;
        });

        headerCb.checked = allChecked;
        if (headerBox) {
            headerBox.classList.toggle("is-checked", allChecked);
        }
    }

    function initDifficulty() {
        var buttons = document.querySelectorAll("[data-diff-btn]");
        var input = document.getElementById("id_setup_difficulty");
        if (!buttons.length || !input) return;

        buttons.forEach(function (btn) {
            btn.addEventListener("click", function () {
                var diff = btn.getAttribute("data-diff-btn");
                input.value = diff;

                buttons.forEach(function (b) {
                    var active = b === btn;
                    b.classList.toggle("is-selected", active);
                });
            });
        });
    }

    function initStepper() {
        var minusBtn = document.getElementById("q-stepper-minus");
        var plusBtn = document.getElementById("q-stepper-plus");
        var display = document.getElementById("q-stepper-display");
        var input = document.getElementById("id_questions_per_subject");
        if (!input) return;

        function setQuestions(val) {
            val = Math.max(1, Math.min(20, val));
            input.value = String(val);
            if (display) display.textContent = String(val);
            updateSummary();
        }

        if (minusBtn) {
            minusBtn.addEventListener("click", function () {
                var current = parseInt(input.value, 10) || 3;
                setQuestions(current - 1);
            });
        }

        if (plusBtn) {
            plusBtn.addEventListener("click", function () {
                var current = parseInt(input.value, 10) || 3;
                setQuestions(current + 1);
            });
        }
    }

    var PRESET_SECONDS = { 0: true, 10: true, 15: true, 30: true, 45: true, 60: true, 90: true };
    var DIFF_LABELS = {
        easy: "Beginner",
        medium: "Intermediate",
        hard: "Advanced",
    };

    var TIMER_STEP = 5;
    var TIMER_MAX = 120;

    function initTimer() {
        var pills = document.querySelectorAll("[data-timer-preset]");
        var input = document.getElementById("id_setup_seconds");
        var display = document.getElementById("t-stepper-display");
        var minusBtn = document.getElementById("t-stepper-minus");
        var plusBtn = document.getElementById("t-stepper-plus");
        var stepper = document.querySelector("[data-timer-stepper]");
        var section = document.querySelector("[data-timer-section]");
        if (!input) return;

        function normalizeTimer(raw) {
            var val = parseInt(raw, 10);
            if (isNaN(val) || val < 0) val = 15;
            if (val === 0) return 0;
            if (val < 10) val = 10;
            if (val > 120) val = 120;
            return val;
        }

        // Any value that is not a preset counts as custom: no pill stays
        // selected and the stepper itself shows the custom state.
        function syncTimerUI(val) {
            var isCustom = !PRESET_SECONDS[val];
            pills.forEach(function (pill) {
                pill.classList.toggle(
                    "is-selected",
                    !isCustom && parseInt(pill.getAttribute("data-timer-preset"), 10) === val
                );
            });
            if (stepper) stepper.classList.toggle("is-custom", isCustom);
            if (display) display.textContent = val === 0 ? "Off" : val + "s";
        }

        function setTimer(val) {
            val = normalizeTimer(val);
            input.value = String(val);
            syncTimerUI(val);
            updateSummary();
        }

        // Instructor-configured timer: show value but block student changes.
        if (section && section.getAttribute("data-timer-locked") === "1") {
            var locked = parseInt(section.getAttribute("data-instructor-seconds"), 10);
            if (!isNaN(locked)) {
                input.value = String(locked);
                syncTimerUI(locked);
            }
            pills.forEach(function (pill) {
                pill.disabled = true;
            });
            if (minusBtn) minusBtn.disabled = true;
            if (plusBtn) plusBtn.disabled = true;
            return;
        }

        pills.forEach(function (pill) {
            pill.addEventListener("click", function () {
                setTimer(pill.getAttribute("data-timer-preset"));
            });
        });

        if (minusBtn) {
            minusBtn.addEventListener("click", function () {
                var current = normalizeTimer(input.value);
                setTimer(current <= 10 ? 0 : current - TIMER_STEP);
            });
        }

        if (plusBtn) {
            plusBtn.addEventListener("click", function () {
                var current = normalizeTimer(input.value);
                setTimer(
                    current === 0
                        ? 10
                        : Math.min(TIMER_MAX, current + TIMER_STEP)
                );
            });
        }

        setTimer(input.value);
    }

    function updateSummary() {
        var form = getForm();
        if (!form) return;

        var maxQ = parseInt(form.getAttribute("data-max-questions"), 10) || 100;
        var qInput = document.getElementById("id_questions_per_subject");
        var qPerSubj = qInput ? parseInt(qInput.value, 10) || 3 : 3;

        var timerInput = document.getElementById("id_setup_seconds");
        var seconds = timerInput ? parseInt(timerInput.value, 10) : 15;
        if (isNaN(seconds) || seconds < 0) seconds = 15;

        var checkedSubjects = form.querySelectorAll("[data-subject-checkbox]:checked").length;
        var totalQuestions = Math.min(maxQ, Math.max(checkedSubjects, 1) * qPerSubj);
        var estMinutes =
            seconds === 0
                ? null
                : Math.max(1, Math.ceil((totalQuestions * seconds) / 60));

        form.querySelectorAll("[data-summary-subjects]").forEach(function (el) {
            el.textContent = String(checkedSubjects);
        });
        form.querySelectorAll("[data-summary-questions]").forEach(function (el) {
            el.textContent = String(totalQuestions);
        });
        form.querySelectorAll("[data-summary-minutes]").forEach(function (el) {
            el.textContent =
                estMinutes == null ? "Untimed" : "~" + estMinutes + " min";
        });

        var selectedCountEl = form.querySelector("[data-selected-count]");
        if (selectedCountEl) {
            selectedCountEl.textContent = String(checkedSubjects);
        }

        var diffInput = document.getElementById("id_setup_difficulty");
        var reviewDiff = form.querySelector("[data-review-difficulty]");
        if (reviewDiff && diffInput) {
            reviewDiff.textContent = DIFF_LABELS[diffInput.value] || diffInput.value;
        }
        var reviewQ = form.querySelector("[data-review-questions-per]");
        if (reviewQ) reviewQ.textContent = String(qPerSubj);
        var reviewTimer = form.querySelector("[data-review-timer]");
        if (reviewTimer) {
            reviewTimer.textContent = seconds === 0 ? "Off" : seconds + " sec";
        }
    }

    function initHowAccordion() {
        var root = document.querySelector("[data-how-accordion]");
        var toggle = document.querySelector("[data-how-toggle]");
        var body = document.querySelector("[data-how-body]");
        if (!root || !toggle || !body) return;

        toggle.addEventListener("click", function () {
            var open = root.classList.toggle("is-open");
            toggle.setAttribute("aria-expanded", open ? "true" : "false");
        });
    }

    function initWizard() {
        var form = getForm();
        if (!form || !form.hasAttribute("data-setup-wizard")) return;

        var step = 1;
        var panels = form.querySelectorAll("[data-step-panel]");
        var stepBtns = form.querySelectorAll("[data-goto-step]");
        var backBtn = form.querySelector("[data-setup-back]");
        var nextBtn = form.querySelector("[data-setup-next]");
        var startBtn = form.querySelector("[data-setup-start]");

        function showStep(next) {
            step = Math.min(3, Math.max(1, next));
            form.setAttribute("data-current-step", String(step));
            panels.forEach(function (panel) {
                var n = parseInt(panel.getAttribute("data-step-panel"), 10);
                panel.classList.toggle("is-active-step", n === step);
            });
            stepBtns.forEach(function (btn) {
                var n = parseInt(btn.getAttribute("data-goto-step"), 10);
                var active = n === step;
                btn.classList.toggle("is-active", active);
                if (active) btn.setAttribute("aria-current", "step");
                else btn.removeAttribute("aria-current");
                btn.classList.toggle("is-complete", n < step);
            });
            if (backBtn) backBtn.hidden = step === 1;
            if (nextBtn) nextBtn.hidden = step === 3;
            if (startBtn) startBtn.hidden = step !== 3;
            updateSummary();
        }

        stepBtns.forEach(function (btn) {
            btn.addEventListener("click", function () {
                showStep(parseInt(btn.getAttribute("data-goto-step"), 10));
            });
        });
        if (backBtn) {
            backBtn.addEventListener("click", function () {
                showStep(step - 1);
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener("click", function () {
                if (step === 1) {
                    var checked = form.querySelectorAll(
                        "[data-subject-checkbox]:checked"
                    ).length;
                    if (!checked) {
                        if (typeof showToast === "function") {
                            showToast("Select at least one subject.", "error");
                        }
                        return;
                    }
                }
                showStep(step + 1);
            });
        }

        showStep(1);
    }

    function init() {
        initTabs();
        initSearch();
        initRowsAndCheckboxes();
        initHeaderCheckbox();
        initDifficulty();
        initStepper();
        initTimer();
        initHowAccordion();
        initWizard();
        filterRows();
        updateSummary();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
