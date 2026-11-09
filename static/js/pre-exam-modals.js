/**
 * Pre-exam wizard on the review setup page (confirm → start).
 */
(function () {
    "use strict";

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

        const readyStart = document.getElementById("pre-exam-ready-start");
        const readyCancel = document.getElementById("pre-exam-ready-cancel");

        function submitForm() {
            hideAll();
            form.dataset.preExamConfirmed = "1";
            form.submit();
        }

        function startPreExamWizard() {
            // The goal step was removed; go straight to the start confirmation.
            showStep("pre-exam-step-ready");
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
