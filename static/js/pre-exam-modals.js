/**
 * Pre-exam wizard on the review setup page (confidence → warm-up → goal → confirm).
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

        const confidenceInput = form.querySelector("#id_pre_session_confidence");
        const goalInput = form.querySelector("#id_session_goal");
        const warmupDataEl = document.getElementById("pre-exam-warmup-data");
        let warmupData = null;
        if (warmupDataEl && warmupDataEl.textContent) {
            try {
                warmupData = JSON.parse(warmupDataEl.textContent);
            } catch (e) {
                warmupData = null;
            }
        }

        const goalContinue = document.getElementById("pre-exam-goal-continue");
        const readyStart = document.getElementById("pre-exam-ready-start");
        const readyCancel = document.getElementById("pre-exam-ready-cancel");
        const warmupContinue = document.getElementById("pre-exam-warmup-continue");
        const warmupStem = document.getElementById("pre-exam-warmup-stem");
        const warmupChoices = document.getElementById("pre-exam-warmup-choices");
        const warmupFeedback = document.getElementById("pre-exam-warmup-feedback");
        const skipGoalCheckbox = document.getElementById("pre-exam-skip-goal");

        let warmupAnswered = false;

        function submitForm() {
            hideAll();
            form.dataset.preExamConfirmed = "1";
            form.submit();
        }

        function setupWarmup() {
            if (!warmupData || !warmupStem || !warmupChoices) {
                afterWarmup();
                return;
            }
            warmupAnswered = false;
            warmupStem.textContent = warmupData.stem;
            warmupChoices.innerHTML = "";
            if (warmupFeedback) {
                warmupFeedback.classList.add("hidden");
                warmupFeedback.textContent = "";
            }
            if (warmupContinue) {
                warmupContinue.classList.add("hidden");
                warmupContinue.disabled = true;
            }
            warmupData.choices.forEach(function (choice) {
                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = "pre-exam-warmup-choice";
                btn.textContent = choice.text;
                btn.dataset.index = String(choice.index);
                btn.addEventListener("click", function () {
                    if (warmupAnswered) return;
                    warmupAnswered = true;
                    const correct = parseInt(choice.index, 10) === warmupData.correct_index;
                    warmupChoices.querySelectorAll("button").forEach(function (b) {
                        b.disabled = true;
                        if (parseInt(b.dataset.index, 10) === warmupData.correct_index) {
                            b.classList.add("pre-exam-warmup-choice--correct");
                        } else if (b === btn && !correct) {
                            b.classList.add("pre-exam-warmup-choice--wrong");
                        }
                    });
                    if (warmupFeedback) {
                        warmupFeedback.textContent = correct
                            ? warmupData.feedback_correct
                            : warmupData.feedback_incorrect;
                        warmupFeedback.classList.remove("hidden");
                        warmupFeedback.classList.toggle(
                            "pre-exam-warmup-feedback--correct",
                            correct
                        );
                        warmupFeedback.classList.toggle(
                            "pre-exam-warmup-feedback--wrong",
                            !correct
                        );
                    }
                    if (warmupContinue) {
                        warmupContinue.classList.remove("hidden");
                        warmupContinue.disabled = false;
                        warmupContinue.focus();
                    }
                });
                warmupChoices.appendChild(btn);
            });
            showStep("pre-exam-step-warmup");
        }

        function afterWarmup() {
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

        document.querySelectorAll("[data-confidence]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                if (confidenceInput) {
                    confidenceInput.value = btn.dataset.confidence || "";
                }
                setupWarmup();
            });
        });

        if (warmupContinue) {
            warmupContinue.addEventListener("click", afterWarmup);
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
            showStep("pre-exam-step-confidence");
        });
    }

    document.addEventListener("DOMContentLoaded", initPreExamModals);
})();
