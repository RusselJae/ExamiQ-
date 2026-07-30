/**
 * Faculty Feedback — student concern modal with chat-style conversation.
 */
(function () {
    "use strict";

    var MAX_IMAGE_BYTES = 5 * 1024 * 1024;
    var ALLOWED_IMAGE_TYPES = {
        "image/jpeg": true,
        "image/png": true,
        "image/webp": true,
    };

    var state = {
        items: [],
        activeMistakeId: null,
        screen: "conversation",
        loaded: false,
        sending: false,
    };

    function config() {
        return window.ExamiQFacultyFeedback || {};
    }

    function escapeHtml(text) {
        var div = document.createElement("div");
        div.textContent = text || "";
        return div.innerHTML;
    }

    function truncateStem(stem) {
        if (!stem) return "Question";
        return stem.length > 80 ? stem.slice(0, 77) + "…" : stem;
    }

    function noteUrl(mistakeId) {
        return (config().noteUrlBase || "").replace("/0/", "/" + mistakeId + "/");
    }

    function activeItem() {
        return state.items.find(function (item) {
            return item.mistake_id === state.activeMistakeId;
        });
    }

    function initialsFor(item) {
        if (item && item.student_initials) return item.student_initials;
        var name = (item && item.student_name) || "?";
        var parts = name.trim().split(/\s+/);
        if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
        return name.slice(0, 2).toUpperCase();
    }

    function openModal() {
        var modal = document.getElementById("faculty-concern-modal");
        if (!modal) return;
        modal.classList.remove("hidden");
        document.body.classList.add("ai-tutor-modal-open");
    }

    function closeModal() {
        var modal = document.getElementById("faculty-concern-modal");
        if (!modal) return;
        modal.classList.add("hidden");
        document.body.classList.remove("ai-tutor-modal-open");
    }

    function setScreen(screen) {
        state.screen = screen === "ai" ? "ai" : "conversation";
        var ai = document.getElementById("faculty-screen-ai");
        var conversation = document.getElementById("faculty-screen-conversation");
        if (ai) ai.classList.toggle("hidden", state.screen !== "ai");
        if (conversation) conversation.classList.toggle("hidden", state.screen !== "conversation");
        document.querySelectorAll("[data-faculty-screen]").forEach(function (btn) {
            var active = btn.getAttribute("data-faculty-screen") === state.screen;
            btn.classList.toggle("ai-tutor-modal__tab--active", active);
            btn.setAttribute("aria-selected", active ? "true" : "false");
        });
    }

    function formatTimestamp(iso) {
        if (!iso) return "";
        try {
            return new Date(iso).toLocaleString();
        } catch (e) {
            return iso;
        }
    }

    function attachmentHtml(msg) {
        if (!msg.image_url) return "";
        var label = msg.image_name || "Attached image";
        return (
            '<a href="' +
            escapeHtml(msg.image_url) +
            '" target="_blank" rel="noopener" class="chat-attach chat-attach--preview">' +
            '<img src="' +
            escapeHtml(msg.image_url) +
            '" alt="' +
            escapeHtml(label) +
            '" class="chat-attach__thumb">' +
            '<span class="chat-attach__meta">' +
            '<span class="chat-attach__label">Attached image</span>' +
            '<span class="chat-attach__name">' +
            escapeHtml(label) +
            "</span></span></a>"
        );
    }

    function renderThread(messages, item) {
        var container = document.getElementById("faculty-concern-thread");
        if (!container) return;
        if (!messages || !messages.length) {
            container.innerHTML =
                '<p class="chat-thread__empty">No messages yet. Send the first reply below.</p>';
            return;
        }
        var studentInitials = initialsFor(item);
        var topic = (item && item.topic) || "";
        container.innerHTML = messages
            .map(function (msg) {
                var isFaculty = msg.author_role === "faculty";
                var side = isFaculty ? "out" : "in";
                var initials = isFaculty
                    ? msg.author_initials || "YOU"
                    : msg.author_initials || studentInitials;
                var header = isFaculty
                    ? "You"
                    : escapeHtml(msg.author_name || "Student") +
                      (topic ? " · " + escapeHtml(topic) : "");
                var bodyHtml = msg.body
                    ? '<p class="chat-bubble__text">' +
                      escapeHtml(msg.body).replace(/\n/g, "<br>") +
                      "</p>"
                    : "";
                return (
                    '<div class="chat-row chat-row--' +
                    side +
                    '">' +
                    (isFaculty
                        ? ""
                        : '<div class="chat-avatar chat-avatar--sm" aria-hidden="true">' +
                          escapeHtml(initials) +
                          "</div>") +
                    '<div class="chat-row__body">' +
                    '<p class="chat-row__header">' +
                    header +
                    "</p>" +
                    '<div class="chat-bubble chat-bubble--' +
                    side +
                    '">' +
                    bodyHtml +
                    attachmentHtml(msg) +
                    "</div>" +
                    '<p class="chat-row__time">' +
                    escapeHtml(formatTimestamp(msg.created_at)) +
                    "</p></div>" +
                    (isFaculty
                        ? '<div class="chat-avatar chat-avatar--sm chat-avatar--self" aria-hidden="true">' +
                          escapeHtml(initials) +
                          "</div>"
                        : "") +
                    "</div>"
                );
            })
            .join("");
        container.scrollTop = container.scrollHeight;
    }

    function renderActive() {
        var item = activeItem();
        if (!item) return;

        var avatar = document.getElementById("faculty-concern-avatar");
        var nameEl = document.getElementById("faculty-concern-student-name");
        var previewEl = document.getElementById("faculty-concern-q-preview");
        var studentEl = document.getElementById("faculty-concern-student");
        var stemEl = document.getElementById("faculty-concern-stem");
        var userEl = document.getElementById("faculty-concern-user-answer");
        var correctEl = document.getElementById("faculty-concern-correct-answer");
        var aiEl = document.getElementById("faculty-concern-ai-feedback");
        var input = document.getElementById("faculty-concern-note-input");

        if (avatar) avatar.textContent = initialsFor(item);
        if (nameEl) nameEl.textContent = item.student_name;
        if (previewEl) previewEl.textContent = "Q: " + truncateStem(item.stem);
        if (studentEl) {
            studentEl.textContent =
                item.student_name + " · " + item.student_email + " · " + item.topic;
        }
        if (stemEl) stemEl.textContent = item.stem;
        if (userEl) userEl.textContent = item.user_answer || "—";
        if (correctEl) correctEl.textContent = item.correct_answer || "—";
        if (aiEl) {
            aiEl.innerHTML = escapeHtml(
                item.ai_feedback || "No AI feedback generated yet."
            ).replace(/\n/g, "<br>");
        }
        if (input) input.value = "";
        clearImageSelection();
        renderThread(item.messages || [], item);
    }

    async function loadConcerns(preferredId) {
        var url = config().concernsUrl || "";
        if (preferredId) {
            url +=
                (url.indexOf("?") >= 0 ? "&" : "?") +
                "mistake_id=" +
                encodeURIComponent(preferredId);
        }
        var resp = await fetch(url, {
            headers: { Accept: "application/json" },
            credentials: "same-origin",
        });
        if (!resp.ok) throw new Error("Could not load concerns.");
        var data = await resp.json();
        state.items = data.items || [];
        state.activeMistakeId =
            preferredId ||
            data.active_mistake_id ||
            (state.items[0] && state.items[0].mistake_id);
    }

    async function openConcern(mistakeId, screen) {
        openModal();
        setScreen(screen || "conversation");
        var loading = document.getElementById("faculty-concern-loading");
        var content = document.getElementById("faculty-concern-content");
        var errorEl = document.getElementById("faculty-concern-error");
        if (loading) loading.classList.remove("hidden");
        if (content) content.classList.add("hidden");
        if (errorEl) errorEl.classList.add("hidden");

        try {
            await loadConcerns(mistakeId);
            if (!state.items.length) {
                throw new Error("No student concerns found.");
            }
            renderActive();
            if (loading) loading.classList.add("hidden");
            if (content) content.classList.remove("hidden");
            state.loaded = true;
            var input = document.getElementById("faculty-concern-note-input");
            if (input && state.screen === "conversation") input.focus();
        } catch (err) {
            if (loading) loading.classList.add("hidden");
            if (errorEl) {
                errorEl.textContent = err.message || "Failed to load concerns.";
                errorEl.classList.remove("hidden");
            }
        }
    }

    function clearImageSelection() {
        var input = document.getElementById("faculty-concern-image");
        var nameEl = document.getElementById("faculty-concern-image-name");
        if (input) input.value = "";
        if (nameEl) {
            nameEl.textContent = "";
            nameEl.classList.add("hidden");
        }
    }

    function validateImageFile(file) {
        if (!file) return null;
        if (file.size > MAX_IMAGE_BYTES) return "Image must be 5 MB or smaller.";
        var type = (file.type || "").toLowerCase();
        var name = (file.name || "").toLowerCase();
        var okType = ALLOWED_IMAGE_TYPES[type];
        var okExt = /\.(jpe?g|png|webp)$/.test(name);
        if (!okType && !okExt) return "Use a JPEG, PNG, or WebP image.";
        return null;
    }

    async function saveNote() {
        var item = activeItem();
        var input = document.getElementById("faculty-concern-note-input");
        var imageInput = document.getElementById("faculty-concern-image");
        var btn = document.getElementById("faculty-concern-save-btn");
        if (!item || !input || state.sending) return;
        var body = (input.value || "").trim();
        var imageFile = imageInput && imageInput.files ? imageInput.files[0] : null;
        if (!body && !imageFile) {
            if (typeof showToast === "function") {
                showToast("Add a reply or photo.", "warning");
            }
            return;
        }
        var imageError = validateImageFile(imageFile);
        if (imageError) {
            if (typeof showToast === "function") showToast(imageError, "error");
            return;
        }
        state.sending = true;
        if (btn) btn.disabled = true;
        try {
            var fd = new FormData();
            fd.append("csrfmiddlewaretoken", config().csrfToken || "");
            fd.append("faculty_note", body);
            fd.append("body", body);
            if (imageFile) fd.append("image", imageFile);
            var resp = await fetch(noteUrl(item.mistake_id), {
                method: "POST",
                body: fd,
                headers: {
                    Accept: "application/json",
                    "X-CSRFToken": config().csrfToken || "",
                },
                credentials: "same-origin",
            });
            var data = await resp.json().catch(function () {
                return {};
            });
            if (!resp.ok) throw new Error(data.error || "Could not send reply.");
            var updated = data.item;
            var idx = state.items.findIndex(function (entry) {
                return entry.mistake_id === updated.mistake_id;
            });
            if (idx >= 0) state.items[idx] = updated;
            renderActive();
            if (typeof showToast === "function") showToast("Reply sent.", "success");
        } catch (err) {
            if (typeof showToast === "function") {
                showToast(err.message || "Could not send reply.", "error");
            }
        } finally {
            state.sending = false;
            if (btn) btn.disabled = false;
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-dismiss-faculty-concern]").forEach(function (el) {
            el.addEventListener("click", closeModal);
        });
        document.querySelectorAll(".open-concern-btn").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var id = parseInt(btn.getAttribute("data-mistake-id"), 10);
                openConcern(id, "conversation");
            });
        });
        document.querySelectorAll("[data-faculty-screen]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                setScreen(btn.getAttribute("data-faculty-screen"));
            });
        });
        var saveBtn = document.getElementById("faculty-concern-save-btn");
        if (saveBtn) saveBtn.addEventListener("click", saveNote);

        var input = document.getElementById("faculty-concern-note-input");
        if (input) {
            input.addEventListener("keydown", function (event) {
                if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    saveNote();
                }
            });
        }

        var imageInput = document.getElementById("faculty-concern-image");
        var imageName = document.getElementById("faculty-concern-image-name");
        if (imageInput) {
            imageInput.addEventListener("change", function () {
                var file = imageInput.files && imageInput.files[0];
                if (!file) {
                    clearImageSelection();
                    return;
                }
                var err = validateImageFile(file);
                if (err) {
                    if (typeof showToast === "function") showToast(err, "error");
                    clearImageSelection();
                    return;
                }
                if (imageName) {
                    imageName.textContent =
                        file.name + " (" + Math.round(file.size / 1024) + " KB)";
                    imageName.classList.remove("hidden");
                }
            });
        }

        var params = new URLSearchParams(window.location.search);
        var mid = params.get("mistake_id");
        if (mid && document.getElementById("faculty-concern-modal")) {
            openConcern(parseInt(mid, 10), "conversation");
        }
    });
})();
