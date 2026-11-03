/* Question modal — Add / Edit question dialogs matching screenshot design. */
(function () {
    "use strict";

    function openModal(modal) {
        modal.classList.remove("hidden");
        document.body.style.overflow = "hidden";
        const firstField = modal.querySelector(
            "input:not([type='hidden']), textarea, select, button"
        );
        if (firstField) firstField.focus();
    }

    function closeModal(modal) {
        modal.classList.add("hidden");
        if (
            !document.querySelector(
                ".question-modal:not(.hidden), .content-modal:not(.hidden)"
            )
        ) {
            document.body.style.overflow = "";
        }
    }

    function dismissOverlay(modal) {
        // Dedicated create/edit pages open the modal as the whole page;
        // closing should leave the previous screen, not an empty shell.
        if (modal.dataset.autoOpen === "1") {
            const cancelUrl =
                modal.dataset.cancelUrl ||
                (modal.querySelector("[data-editor-cancel]") &&
                    modal
                        .querySelector("[data-editor-cancel]")
                        .getAttribute("data-cancel-url"));
            if (cancelUrl) {
                window.location.href = cancelUrl;
                return;
            }
            if (window.history.length > 1) {
                window.history.back();
                return;
            }
            window.location.href = "/";
            return;
        }
        closeModal(modal);
    }

    function setupModal(modal) {
        const form = modal.querySelector(".question-modal__inner");

        modal.querySelectorAll("[data-dismiss-content]").forEach((el) => {
            el.addEventListener("click", () => dismissOverlay(modal));
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && !modal.classList.contains("hidden")) {
                dismissOverlay(modal);
            }
        });

        const difficultyPills = modal.querySelectorAll("[data-difficulty-value]");
        difficultyPills.forEach((pill) => {
            pill.addEventListener("click", () => {
                difficultyPills.forEach((p) =>
                    p.classList.remove("question-modal__difficulty-pill--active")
                );
                pill.classList.add("question-modal__difficulty-pill--active");
                const hidden = modal.querySelector(
                    ".question-modal__field-hidden [name='difficulty'], [name='difficulty']"
                );
                if (hidden && hidden.tagName === "SELECT") {
                    hidden.value = pill.dataset.difficultyValue;
                } else if (hidden) {
                    hidden.value = pill.dataset.difficultyValue;
                }
                const radio = modal.querySelector(
                    `input[type="radio"][name="difficulty"][value="${pill.dataset.difficultyValue}"]`
                );
                if (radio) radio.checked = true;
            });
        });

        const actionBtn = modal.querySelector(".question-modal__action");
        if (actionBtn && form && !actionBtn.getAttribute("form")) {
            actionBtn.addEventListener("click", (event) => {
                event.preventDefault();
                form.requestSubmit();
            });
        }

        const cancelBtn = modal.querySelector("[data-editor-cancel]");
        if (cancelBtn) {
            cancelBtn.addEventListener("click", () => dismissOverlay(modal));
        }
    }

    function applyTriggerMeta(modal, trigger) {
        const title = trigger.dataset.questionModalTitle;
        const action = trigger.dataset.questionModalAction;
        const titleEl = modal.querySelector(".question-modal__title");
        const actionEl = modal.querySelector(".question-modal__action");
        if (title && titleEl) titleEl.textContent = title;
        if (action && actionEl) actionEl.textContent = action;

        const form = modal.querySelector(".question-modal__inner");
        const coursePk = trigger.dataset.coursePk || modal.dataset.coursePk;
        const questionPk = trigger.dataset.questionModalQuestionPk;
        if (form && coursePk && questionPk) {
            form.action = `/courses/${coursePk}/questions/${questionPk}/edit/`;
        } else if (form && coursePk && trigger.dataset.questionModal === "add") {
            const singleUrl = trigger.dataset.formAction;
            if (singleUrl) form.action = singleUrl;
        }
    }

    function initBatchHost() {
        const host = document.getElementById("batch-host-modal");
        if (!host) return;
        const frame = host.querySelector("[data-batch-frame]");

        function openBatch(src) {
            if (frame && src) frame.src = src;
            host.classList.remove("hidden");
            document.body.style.overflow = "hidden";
        }

        function closeBatch() {
            host.classList.add("hidden");
            if (frame) frame.src = "about:blank";
            if (
                !document.querySelector(
                    ".question-modal:not(.hidden), .content-modal:not(.hidden)"
                )
            ) {
                document.body.style.overflow = "";
            }
        }

        host.querySelectorAll("[data-dismiss-batch]").forEach((el) => {
            el.addEventListener("click", closeBatch);
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && !host.classList.contains("hidden")) {
                closeBatch();
            }
        });

        document.querySelectorAll("[data-batch-modal]").forEach((trigger) => {
            trigger.addEventListener("click", (event) => {
                event.preventDefault();
                event.stopPropagation();
                const src =
                    trigger.dataset.batchModalSrc ||
                    trigger.getAttribute("href") ||
                    "";
                if (!src) return;
                openBatch(src);
            });
        });

        window.addEventListener("message", (event) => {
            if (event.origin !== window.location.origin) return;
            if (event.data && event.data.type === "examiq-batch-close") {
                closeBatch();
            }
        });
    }

    function init() {
        document
            .querySelectorAll(".question-modal:not(.batch-host-modal)")
            .forEach(setupModal);

        document.querySelectorAll("[data-question-modal]").forEach((trigger) => {
            trigger.addEventListener("click", (event) => {
                const mode = trigger.dataset.questionModal; // "add" | "edit"
                const modal = document.getElementById(`question-modal-${mode}`);
                if (!modal) return;
                event.preventDefault();
                applyTriggerMeta(modal, trigger);
                openModal(modal);
            });
        });

        // Dedicated create/edit pages: lock body while the overlay is open.
        document
            .querySelectorAll(".question-modal[data-auto-open='1']")
            .forEach((modal) => {
                openModal(modal);
            });

        initBatchHost();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
