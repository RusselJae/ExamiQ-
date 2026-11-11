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
            const removeBtn = modal.querySelector("[data-dropzone-remove]");

            if (dropzone) {
                dropzone.addEventListener("click", (event) => {
                    if (event.target.closest("[data-dropzone-remove]")) return;
                    fileInput.click();
                });
                dropzone.addEventListener("keydown", (event) => {
                    if (event.target.closest("[data-dropzone-remove]")) return;
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
            if (removeBtn) {
                removeBtn.addEventListener("click", (event) => {
                    event.stopPropagation();
                    try {
                        fileInput.value = "";
                    } catch (e) { /* ignore */ }
                    resetSelectedFile(modal);
                });
            }
        }

        // Edit mode: removal opens the replacement upload UI.
        if (replaceInput) {
            const actionInput = modal.querySelector("[data-modal-action-input]");
            const attachedCard = modal.querySelector("[data-attached-card]");
            const replaceDropzone = modal.querySelector("[data-replace-dropzone]");
            const removeBtn = modal.querySelector("[data-attached-remove]");
            const replaceHint = modal.querySelector("[data-replace-hint]");

            if (removeBtn) {
                removeBtn.addEventListener("click", () => {
                    if (attachedCard) attachedCard.classList.add("hidden");
                    if (replaceDropzone) replaceDropzone.classList.remove("hidden");
                    if (replaceHint) {
                        replaceHint.textContent =
                            "Choose a new PDF to replace the removed file. The title stays the same.";
                    }
                    replaceInput.click();
                });
            }
            if (replaceDropzone) {
                replaceDropzone.addEventListener("click", () => replaceInput.click());
                replaceDropzone.addEventListener("keydown", (event) => {
                    if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        replaceInput.click();
                    }
                });
            }
            replaceInput.addEventListener("change", () => {
                if (!replaceInput.files || !replaceInput.files.length) return;
                const file = replaceInput.files[0];
                const maxMb = parseFloat(replaceInput.dataset.maxSizeMb || "0");
                if (maxMb && file.size > maxMb * 1024 * 1024) {
                    if (replaceHint) {
                        replaceHint.textContent =
                            `That PDF is larger than ${maxMb} MB. Compress it first.`;
                        replaceHint.classList.add("content-modal__helper--error");
                    }
                    try {
                        replaceInput.value = "";
                    } catch (e) { /* ignore */ }
                    return;
                }
                const ext = (file.name.split(".").pop() || "FILE").toUpperCase();
                const extEl = modal.querySelector("[data-attached-ext]");
                const nameEl = modal.querySelector("[data-attached-name]");
                const metaEl = modal.querySelector("[data-attached-meta]");
                if (extEl) {
                    extEl.textContent = ext.slice(0, 8);
                    extEl.className = `content-modal__badge content-modal__badge--${ext.toLowerCase()}`;
                }
                if (nameEl) nameEl.textContent = file.name;
                if (metaEl) {
                    metaEl.textContent =
                        "Selected — saving will replace the current file";
                }
                if (attachedCard) attachedCard.classList.remove("hidden");
                if (replaceDropzone) replaceDropzone.classList.add("hidden");
                if (actionInput) actionInput.value = "replace_file";
                if (form) form.requestSubmit();
            });
        }
    }

    function resetSelectedFile(modal) {
        const empty = modal.querySelector("[data-dropzone-empty]");
        const attached = modal.querySelector("[data-dropzone-attached]");
        const dropzone = modal.querySelector("[data-dropzone]");
        const helperEl = modal.querySelector("[data-modal-file-helper]");
        const nameEl = modal.querySelector("[data-dropzone-filename]");
        const metaEl = modal.querySelector("[data-dropzone-filemeta]");
        const originalNameInput = modal.querySelector("[data-modal-original-name]");
        if (empty) empty.classList.remove("hidden");
        if (attached) attached.classList.add("hidden");
        if (dropzone) dropzone.classList.remove("has-file");
        if (nameEl) nameEl.textContent = "";
        if (metaEl) metaEl.textContent = "";
        if (originalNameInput) originalNameInput.value = "";
        if (helperEl) {
            helperEl.classList.remove("content-modal__helper--error");
            helperEl.textContent = "Choose a PDF that matches this course subject.";
        }
    }

    function reflectSelectedFile(fileInput, originalNameInput, titleInput) {
        if (!fileInput.files || !fileInput.files.length) {
            resetSelectedFile(fileInput.closest(".content-modal"));
            return;
        }
        const file = fileInput.files[0];
        const modal = fileInput.closest(".content-modal");
        const maxMb = parseFloat(fileInput.dataset.maxSizeMb || "0");
        const helperEl = modal ? modal.querySelector("[data-modal-file-helper]") : null;
        if (maxMb && file.size > maxMb * 1024 * 1024) {
            try {
                fileInput.value = "";
            } catch (e) { /* ignore */ }
            resetSelectedFile(modal);
            if (helperEl) {
                helperEl.classList.add("content-modal__helper--error");
                helperEl.textContent =
                    `That PDF is larger than ${maxMb} MB. Compress it and try again.`;
            }
            return;
        }
        if (originalNameInput) originalNameInput.value = file.name;
        if (titleInput && !titleInput.value.trim()) {
            titleInput.value = file.name.replace(/\.[^.]+$/, "");
        }
        const empty = modal ? modal.querySelector("[data-dropzone-empty]") : null;
        const attached = modal ? modal.querySelector("[data-dropzone-attached]") : null;
        const nameEl = modal ? modal.querySelector("[data-dropzone-filename]") : null;
        const metaEl = modal ? modal.querySelector("[data-dropzone-filemeta]") : null;
        if (empty) empty.classList.add("hidden");
        if (attached) attached.classList.remove("hidden");
        if (nameEl) {
            nameEl.textContent = file.name;
            nameEl.title = file.name;
        }
        if (metaEl) {
            metaEl.textContent = `${formatBytes(file.size) || "PDF"} · Ready to upload`;
        }
        const dropzone = modal ? modal.querySelector("[data-dropzone]") : null;
        if (dropzone) dropzone.classList.add("has-file");
        // A fresh pick clears a previous server-side mismatch message; the
        // file is validated again on submit.
        if (helperEl) {
            helperEl.classList.remove("content-modal__helper--error");
            helperEl.textContent =
                "Choose a PDF that matches this course subject.";
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
