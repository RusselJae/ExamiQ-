/**
 * Pre-exam wizard on the review setup page (goal → confirm).
 */
(function () {
    "use strict";

    const GOAL_SKIP_KEY = "examiq-pre-exam-goal-skip";

    function showStep(id) {
        document.querySelectorAll(".pre-exam-modal").forEach(function (el) {
            el.classList.add("hidden");
        });
        const step = document.getElementById(id);
        if (step) {
            step.classList.remove("hidden");
        }
        const root = document.getElementById("pre-exam-modals");
        if (root) {
            root.setAttribute("aria-hidden", "false");
        }
    }

    function hideAll() {
        document.querySelectorAll(".pre-exam-modal").forEach(function (el) {
            el.classList.add("hidden");
        });
        const root = document.getElementById("pre-exam-modals");
        if (root) {
            root.setAttribute("aria-hidden", "true");
        }
    }

    function initPreExamModals() {
        const form = document.getElementById("review-setup-form");
        if (!form || form.dataset.preExamBound) return;
        form.dataset.preExamBound = "1";

        const goalInput = form.querySelector("#id_session_goal");
        const goalContinue = document.getElementById("pre-exam-goal-continue");
        const readyStart = document.getElementById("pre-exam-ready-start");
        const readyCancel = document.getElementById("pre-exam-ready-cancel");
        const skipGoalCheckbox = document.getElementById("pre-exam-skip-goal");

        function submitForm() {
            hideAll();
            form.dataset.preExamConfirmed = "1";
            form.submit();
        }

        function startPreExamWizard() {
            let skipGoal = false;
            try {
                skipGoal = localStorage.getItem(GOAL_SKIP_KEY) === "1";
            } catch (e) {
                skipGoal = false;
            }
            if (skipGoal) {
                showStep("pre-exam-step-ready");
            } else {
                showStep("pre-exam-step-goal");
            }
        }

        document.querySelectorAll('input[name="pre_exam_goal"]').forEach(function (radio) {
            radio.addEventListener("change", function () {
                if (goalInput) {
                    goalInput.value = radio.value;
                }
                if (goalContinue) {
                    goalContinue.disabled = false;
                }
            });
        });

        if (goalContinue) {
            goalContinue.addEventListener("click", function () {
                if (skipGoalCheckbox && skipGoalCheckbox.checked) {
                    try {
                        localStorage.setItem(GOAL_SKIP_KEY, "1");
                    } catch (e) {
                        /* ignore */
                    }
                }
                showStep("pre-exam-step-ready");
            });
        }

        if (readyCancel) {
            readyCancel.addEventListener("click", hideAll);
        }

        if (readyStart) {
            readyStart.addEventListener("click", submitForm);
        }

        document.querySelectorAll("[data-pre-exam-dismiss]").forEach(function (el) {
            el.addEventListener("click", hideAll);
        });

        form.addEventListener("submit", function (event) {
            if (form.dataset.preExamConfirmed === "1") return;
            event.preventDefault();
            startPreExamWizard();
        });
    }

    document.addEventListener("DOMContentLoaded", initPreExamModals);
})();
