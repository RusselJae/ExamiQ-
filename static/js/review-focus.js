/**
 * EXAMIQ Review Focus Screen — sidebar toggle, confidence slider, progress
 */
(function () {
    "use strict";

    function initSidebars() {
        document.querySelectorAll(".sidebar-toggle").forEach(function (btn) {
            if (btn.dataset.bound) return;
            btn.dataset.bound = "1";
            btn.addEventListener("click", function () {
                const targetId = btn.dataset.target;
                const sidebar = document.getElementById(targetId);
                if (!sidebar) return;

                sidebar.classList.toggle("collapsed");
                const isCollapsed = sidebar.classList.contains("collapsed");

                if (targetId === "left-sidebar") {
                    sidebar.style.width = isCollapsed ? "3.5rem" : "16rem";
                } else if (targetId === "right-sidebar") {
                    sidebar.style.width = isCollapsed ? "3.5rem" : "14rem";
                }

                sessionStorage.setItem("examiq-" + targetId, isCollapsed ? "1" : "0");
            });
        });

        ["left-sidebar", "right-sidebar"].forEach(function (id) {
            const stored = sessionStorage.getItem("examiq-" + id);
            if (stored === "1") {
                const sidebar = document.getElementById(id);
                if (sidebar) {
                    sidebar.classList.add("collapsed");
                    sidebar.style.width = "3.5rem";
                }
            }
        });
    }

    function updateSliderThumbPosition(slider, label) {
        if (!slider || !label) return;
        const min = parseInt(slider.min, 10) || 1;
        const max = parseInt(slider.max, 10) || 5;
        const val = parseInt(slider.value, 10);
        const percent = ((val - min) / (max - min)) * 100;
        label.style.left = percent + "%";
        label.textContent = String(val);
        slider.setAttribute("aria-valuenow", String(val));
    }

    function initConfidenceSlider(root) {
        const form = (root || document).querySelector("[data-confidence-form]");
        if (!form) return;

        const hiddenInput = form.querySelector("#confidence-input, input[name='confidence']");
        const slider = form.querySelector("#confidence-slider");
        const display = form.querySelector("#confidence-slider-display");
        if (!hiddenInput || !slider) return;

        function syncFromSlider() {
            hiddenInput.value = slider.value;
            updateSliderThumbPosition(slider, display);
        }

        slider.addEventListener("input", syncFromSlider);

        if (hiddenInput.value) {
            slider.value = hiddenInput.value;
        }
        syncFromSlider();
    }

    function initChoiceTiles(root) {
        (root || document).querySelectorAll(".choice-tile").forEach(function (tile) {
            const radio = tile.querySelector('input[type="radio"]');
            if (!radio || radio.dataset.bound) return;
            radio.dataset.bound = "1";
            radio.addEventListener("change", function () {
                document.querySelectorAll(".choice-tile").forEach(function (t) {
                    t.classList.remove("selected");
                });
                if (radio.checked) tile.classList.add("selected");
            });
        });
    }

    function setSessionStatus(status) {
        const statusEl = document.getElementById("session-status");
        const dotEl = document.getElementById("session-status-dot");
        if (!statusEl) return;

        if (status === "feedback") {
            statusEl.textContent = "Reviewing feedback";
            statusEl.dataset.sessionStatus = "feedback";
            if (dotEl) dotEl.classList.add("focus-status-dot--feedback");
        } else {
            statusEl.textContent = "In progress";
            statusEl.dataset.sessionStatus = "in-progress";
            if (dotEl) dotEl.classList.remove("focus-status-dot--feedback");
        }
    }

    function renderQuestionDots(answered, position, planned) {
        const container = document.getElementById("focus-question-dots");
        if (!container || !planned) return;

        container.innerHTML = "";
        for (let i = 1; i <= planned; i++) {
            const dot = document.createElement("span");
            if (i <= answered) {
                dot.className = "focus-dot focus-dot--answered";
                dot.title = "Question " + i + " answered";
                dot.setAttribute("aria-label", "Question " + i + " answered");
                dot.innerHTML =
                    '<svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">' +
                    '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/></svg>';
            } else if (i === position) {
                dot.className = "focus-dot focus-dot--current";
                dot.title = "Question " + i;
                dot.setAttribute("aria-current", "step");
                dot.textContent = String(i);
            } else {
                dot.className = "focus-dot focus-dot--upcoming";
                dot.title = "Question " + i;
                dot.textContent = String(i);
            }
            container.appendChild(dot);
        }
        container.dataset.answered = String(answered);
        container.dataset.position = String(position);
    }

    function updateProgress(answered, planned) {
        const answeredEl = document.getElementById("answered-count");
        const remainingEl = document.getElementById("remaining-count");
        const fillEl = document.getElementById("focus-progress-fill");
        const barEl = document.getElementById("focus-progress-bar");

        if (answeredEl) answeredEl.textContent = String(answered);
        if (remainingEl) remainingEl.textContent = String(Math.max(0, planned - answered));
        if (fillEl && planned) {
            fillEl.style.width = Math.round((answered / planned) * 100) + "%";
        }
        if (barEl) {
            barEl.setAttribute("aria-valuenow", String(answered));
        }

        const position = Math.min(answered + 1, planned || answered + 1);
        renderQuestionDots(answered, position, planned);
    }

    function katexRender(el) {
        if (typeof window.renderMathInElement !== "undefined" && el) {
            window.renderMathInElement(el, {
                delimiters: [
                    { left: "$$", right: "$$", display: true },
                    { left: "$", right: "$", display: false },
                ],
            });
        }
    }

    window.initExplanationAccordion = function (root) {
        const container = root || document.querySelector("[data-explanation-accordion]");
        if (!container) return;

        const steps = container.querySelectorAll(".explanation-step");
        const revealBtn = container.querySelector("[data-reveal-next]");
        const nextQuestionBtn = container.querySelector("[data-next-question]");
        let visibleCount = 1;

        function updateVisibility() {
            steps.forEach(function (step, index) {
                if (index < visibleCount) {
                    step.classList.remove("hidden-step");
                    katexRender(step);
                } else {
                    step.classList.add("hidden-step");
                }
            });

            if (revealBtn) {
                if (visibleCount >= steps.length) {
                    revealBtn.classList.add("hidden");
                    if (nextQuestionBtn) nextQuestionBtn.classList.remove("hidden");
                } else {
                    revealBtn.classList.remove("hidden");
                    if (nextQuestionBtn) nextQuestionBtn.classList.add("hidden");
                }
            } else if (nextQuestionBtn) {
                nextQuestionBtn.classList.remove("hidden");
            }
        }

        if (revealBtn) {
            revealBtn.addEventListener("click", function () {
                if (visibleCount < steps.length) {
                    visibleCount++;
                    updateVisibility();
                    recordStepView(steps[visibleCount - 1]);
                }
            });
        }

        function recordStepView(stepEl) {
            const url = stepEl && stepEl.dataset.stepFeedbackUrl;
            if (!url || stepEl.dataset.recorded) return;
            const csrf = document.querySelector("[name=csrfmiddlewaretoken]");
            const token = csrf ? csrf.value : "";
            fetch(url, {
                method: "POST",
                headers: {
                    "X-CSRFToken": token,
                    "X-Requested-With": "XMLHttpRequest",
                },
                credentials: "same-origin",
            });
            stepEl.dataset.recorded = "1";
        }

        updateVisibility();
        if (steps.length > 0) {
            katexRender(steps[0]);
            recordStepView(steps[0]);
        }
    };

    function handleHtmxAfterSwap(event) {
        const target = event.detail.target;
        if (!target) return;

        initConfidenceSlider(target);
        initChoiceTiles(target);

        const accordion = target.querySelector("[data-explanation-accordion]");
        if (accordion) {
            setSessionStatus("feedback");
            initExplanationAccordion(accordion);

            const dotsEl = document.getElementById("focus-question-dots");
            const planned = dotsEl ? parseInt(dotsEl.dataset.planned, 10) || 0 : 0;
            const answeredEl = document.getElementById("answered-count");
            const currentAnswered = answeredEl ? parseInt(answeredEl.textContent, 10) || 0 : 0;
            const newAnswered = currentAnswered + 1;
            updateProgress(newAnswered, planned);
        } else if (target.querySelector("[data-confidence-form]")) {
            setSessionStatus("in-progress");
        }

        if (target.querySelector(".examiq-math-block")) {
            katexRender(target);
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        initSidebars();
        initConfidenceSlider(document);
        initChoiceTiles(document);

        const questionContainer = document.getElementById("question-container");
        if (questionContainer) {
            initConfidenceSlider(questionContainer);
            initChoiceTiles(questionContainer);
            katexRender(questionContainer);
        }
    });

    document.body.addEventListener("htmx:afterSwap", handleHtmxAfterSwap);
    document.body.addEventListener("htmx:responseError", function () {
        if (typeof showToast === "function") {
            showToast("Something went wrong. Please try again.", "error");
        }
    });

    document.body.addEventListener("htmx:beforeRequest", function (event) {
        const form = event.detail.elt;
        if (!form || !form.matches || !form.matches("[data-confidence-form]")) return;

        const timedOutInput = form.querySelector("#timed-out-input, input[name='timed_out']");
        if (timedOutInput && timedOutInput.value === "true") return;

        const hiddenInput = form.querySelector("input[name='confidence']");
        if (!hiddenInput || !hiddenInput.value) {
            event.preventDefault();
            if (typeof showToast === "function") {
                showToast("Please select your confidence level before submitting.", "warning");
            }
        }
    });
})();
