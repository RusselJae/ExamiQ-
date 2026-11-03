/* Content modal — Add / Edit content dialogs, sized like the AI tutor modal. */
(function () {
    "use strict";

    function formatBytes(bytes) {
        const n = Number(bytes) || 0;
        if (!n) return "";
        if (n >= 1048576) return `${(n / 1048576).toFixed(1)} MB`;
        return `${(n / 1024).toFixed(1)} KB`;
    }

    function openModal(modal) {
        modal.classList.remove("hidden");
        document.body.style.overflow = "hidden";
        const firstField = modal.querySelector("input, textarea, select, button");
        if (firstField) firstField.focus();
    }

    function closeModal(modal) {
        modal.classList.add("hidden");
        if (
            !document.querySelector(
                ".content-modal:not(.hidden), .question-modal:not(.hidden)"
            )
        ) {
            document.body.style.overflow = "";
        }
        /* Server-rendered edit pages (e.g. a material opened directly by URL)
         * host the dialog over an otherwise empty page: closing it returns to
         * the library instead of leaving a blank screen behind. */
        const cancelUrl = modal.getAttribute("data-cancel-url");
        if (cancelUrl) {
            window.location.href = cancelUrl;
        }
    }

    /* ── Per-modal behaviour ─────────────────────────────────────────── */
    function setupModal(modal) {
        const form = modal.querySelector(".content-modal__inner");
        const fileInput = modal.querySelector("[data-modal-file]");
        const replaceInput = modal.querySelector("[data-modal-replace]");
        const actionBtn = modal.querySelector(".content-modal__action");

        // Close: header X + backdrop click + Escape.
        modal.querySelectorAll("[data-dismiss-content]").forEach((el) => {
            el.addEventListener("click", () => closeModal(modal));
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && !modal.classList.contains("hidden")) {
                closeModal(modal);
            }
        });

        // Header action sits outside the form; form= attribute handles submit.
        if (actionBtn && form && !actionBtn.getAttribute("form")) {
            actionBtn.addEventListener("click", (event) => {
                event.preventDefault();
                form.requestSubmit();
            });
        }

        // Add mode: dropzone click / drag & drop.
        if (fileInput) {
            const dropzone = modal.querySelector("[data-dropzone]");
            const originalNameInput = modal.querySelector("[data-modal-original-name]");
            const titleInput = modal.querySelector("[data-modal-title-input]");

            if (dropzone) {
                dropzone.addEventListener("click", () => fileInput.click());
                dropzone.addEventListener("keydown", (event) => {
                    if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        fileInput.click();
                    }
                });
                ["dragover", "dragenter"].forEach((type) => {
                    dropzone.addEventListener(type, (event) => {
                        event.preventDefault();
                        dropzone.classList.add("is-dragging");
                    });
                });
                ["dragleave", "dragend", "drop"].forEach((type) => {
                    dropzone.addEventListener(type, () => {
                        dropzone.classList.remove("is-dragging");
                    });
                });
                dropzone.addEventListener("drop", (event) => {
                    event.preventDefault();
                    const files = event.dataTransfer && event.dataTransfer.files;
                    if (files && files.length) fileInput.files = files;
                    reflectSelectedFile(fileInput, originalNameInput, titleInput);
                });
            }

            fileInput.addEventListener("change", () => {
                reflectSelectedFile(fileInput, originalNameInput, titleInput);
            });
        }

        // Edit mode: replacement file. Submitting with the replacement swaps
        // the upload immediately (the view archives + re-ingests).
        if (replaceInput) {
            const actionInput = modal.querySelector("[data-modal-action-input]");
            const extEl = modal.querySelector("[data-attached-ext]");
            const nameEl = modal.querySelector("[data-attached-name]");
            const metaEl = modal.querySelector("[data-attached-meta]");
            const replaceTrigger = modal.querySelector("[data-replace-file-trigger]");

            if (replaceTrigger) {
                replaceTrigger.addEventListener("click", () => replaceInput.click());
            }
            replaceInput.addEventListener("change", () => {
                if (!replaceInput.files || !replaceInput.files.length) return;
                const file = replaceInput.files[0];
                const ext = (file.name.split(".").pop() || "FILE").toUpperCase();
                if (extEl) {
                    extEl.textContent = ext.slice(0, 8);
                    extEl.className = `content-modal__badge content-modal__badge--${ext.toLowerCase()}`;
                }
                if (nameEl) nameEl.textContent = file.name;
                if (metaEl) {
                    metaEl.textContent =
                        "Selected — saving will replace the current file";
                }
                if (actionInput) actionInput.value = "replace_file";
                if (form) form.requestSubmit();
            });
        }
    }

    function reflectSelectedFile(fileInput, originalNameInput, titleInput) {
        if (!fileInput.files || !fileInput.files.length) return;
        const file = fileInput.files[0];
        if (originalNameInput) originalNameInput.value = file.name;
        if (titleInput && !titleInput.value.trim()) {
            titleInput.value = file.name.replace(/\.[^.]+$/, "");
        }
        const nameEl = fileInput
            .closest(".content-modal")
            ?.querySelector("[data-dropzone-filename]");
        if (nameEl) {
            nameEl.textContent = `${file.name} · ${formatBytes(file.size)}`;
        }
    }

    function applyEditMeta(modal, trigger) {
        const form = modal.querySelector(".content-modal__inner");
        if (!form) return;

        if (trigger.dataset.url) {
            form.action = trigger.dataset.url;
        }

        const titleInput = modal.querySelector("[data-modal-title-input]");
        const descInput = modal.querySelector("[data-modal-description]");
        const nameEl = modal.querySelector("[data-attached-name]");
        const metaEl = modal.querySelector("[data-attached-meta]");
        const extEl = modal.querySelector("[data-attached-ext]");
        const downloadEl = modal.querySelector("[data-attached-download]");
        const subjectHidden = modal.querySelector("[data-modal-subject-input]");
        const subjectLabel = modal.querySelector("[data-sidebar-course]");

        if (titleInput && trigger.dataset.docTitle) {
            titleInput.value = trigger.dataset.docTitle;
        }
        if (descInput && trigger.dataset.docDescription != null) {
            descInput.value = trigger.dataset.docDescription;
        }
        if (nameEl) {
            nameEl.textContent =
                trigger.dataset.docFilename ||
                trigger.dataset.docTitle ||
                "Document";
        }
        if (metaEl) {
            const bits = [];
            if (trigger.dataset.docSize) bits.push(formatBytes(trigger.dataset.docSize));
            if (trigger.dataset.docPages && Number(trigger.dataset.docPages) > 0) {
                bits.push(`${trigger.dataset.docPages} pages`);
            }
            if (trigger.dataset.docCreated) bits.push(trigger.dataset.docCreated);
            metaEl.textContent = bits.join(" · ") || "Attached file";
        }
        if (extEl && trigger.dataset.docExt) {
            const ext = trigger.dataset.docExt.toUpperCase();
            extEl.textContent = ext.slice(0, 8);
            extEl.className = `content-modal__badge content-modal__badge--${ext.toLowerCase()}`;
        }
        if (downloadEl && trigger.dataset.downloadUrl) {
            downloadEl.href = trigger.dataset.downloadUrl;
        }
        if (trigger.dataset.docSubject) {
            if (subjectHidden) subjectHidden.value = trigger.dataset.docSubject;
            if (subjectLabel && trigger.dataset.docSubjectLabel) {
                subjectLabel.textContent = trigger.dataset.docSubjectLabel;
            }
        }
    }

    function init() {
        document.querySelectorAll(".content-modal").forEach(setupModal);

        /* Full-screen edit pages render the dialog pre-filled and ask for it
         * to be opened on load (data-auto-open="1"). */
        document.querySelectorAll(".content-modal[data-auto-open='1']").forEach(
            (modal) => {
                openModal(modal);
            }
        );

        document.querySelectorAll("[data-content-modal]").forEach((trigger) => {
            trigger.addEventListener("click", (event) => {
                const mode = trigger.dataset.contentModal; // "add" | "edit"
                const modal = document.getElementById(`content-modal-${mode}`);
                if (!modal) return;
                event.preventDefault();
                if (mode === "edit") applyEditMeta(modal, trigger);
                openModal(modal);
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
