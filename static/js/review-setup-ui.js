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

    function initTabs() {
        var tabButtons = document.querySelectorAll("[data-tab]");
        tabButtons.forEach(function (btn) {
            btn.addEventListener("click", function () {
                var tab = btn.getAttribute("data-tab");
                if (tab === currentTab) return;

                currentTab = tab;
                tabButtons.forEach(function (b) {
                    var active = b === btn;
                    b.classList.toggle("is-active", active);
                    b.setAttribute("aria-selected", active ? "true" : "false");
                });

                filterRows();
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

    function initTimer() {
        var pills = document.querySelectorAll("[data-timer-preset]");
        var input = document.getElementById("id_setup_seconds");
        var label = document.getElementById("timer-display-label");
        if (!input) return;

        function normalizeTimer(raw) {
            var val = parseInt(raw, 10);
            if (isNaN(val) || val < 0) val = 15;
            if (val === 0) return 0;
            if (val < 10) val = 10;
            if (val > 120) val = 120;
            return val;
        }

        function setTimer(val, syncInput) {
            val = normalizeTimer(val);
            if (syncInput !== false) input.value = String(val);
            if (label) {
                label.textContent = val === 0 ? "No timer" : val + " sec";
            }

            pills.forEach(function (pill) {
                var preset = parseInt(pill.getAttribute("data-timer-preset"), 10);
                pill.classList.toggle("is-selected", preset === val);
            });

            updateSummary();
        }

        pills.forEach(function (pill) {
            pill.addEventListener("click", function () {
                setTimer(pill.getAttribute("data-timer-preset"));
            });
        });

        input.addEventListener("change", function () {
            setTimer(input.value);
        });
        input.addEventListener("input", function () {
            var raw = parseInt(input.value, 10);
            if (isNaN(raw)) return;
            if (label) {
                label.textContent = raw === 0 ? "No timer" : raw + " sec";
            }
            pills.forEach(function (pill) {
                var preset = parseInt(pill.getAttribute("data-timer-preset"), 10);
                pill.classList.toggle("is-selected", preset === raw);
            });
            updateSummary();
        });

        setTimer(input.value, false);
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

        var subjectsEl = form.querySelector("[data-summary-subjects]");
        var questionsEl = form.querySelector("[data-summary-questions]");
        var minutesEl = form.querySelector("[data-summary-minutes]");

        if (subjectsEl) subjectsEl.textContent = String(checkedSubjects);
        if (questionsEl) questionsEl.textContent = String(totalQuestions);
        if (minutesEl) {
            minutesEl.textContent =
                estMinutes == null ? "Untimed" : "~" + estMinutes + " min";
        }
    }

    function init() {
        initTabs();
        initSearch();
        initRowsAndCheckboxes();
        initHeaderCheckbox();
        initDifficulty();
        initStepper();
        initTimer();
        filterRows();
        updateSummary();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
