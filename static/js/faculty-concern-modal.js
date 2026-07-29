/**
 * Faculty Feedback — student concern modal (AI message vs conversation thread).
 */
(function () {
    "use strict";

    var state = {
        items: [],
        activeMistakeId: null,
        screen: "ai",
        loaded: false,
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
        return config().noteUrlBase + mistakeId + "/";
    }

    function activeItem() {
        return state.items.find(function (item) {
            return item.mistake_id === state.activeMistakeId;
        });
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
        state.screen = screen === "conversation" ? "conversation" : "ai";
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

    function renderThread(messages) {
        var container = document.getElementById("faculty-concern-thread");
        if (!container) return;
        if (!messages || !messages.length) {
            container.innerHTML =
                '<p class="text-sm text-examiq-slate">No messages yet.</p>';
            return;
        }
        container.innerHTML = messages
            .map(function (msg) {
                var bodyHtml = msg.body
                    ? '<p class="concern-thread__body whitespace-pre-line">' +
                      escapeHtml(msg.body) +
                      "</p>"
                    : "";
                var imageHtml = msg.image_url
                    ? '<a href="' +
                      escapeHtml(msg.image_url) +
                      '" target="_blank" rel="noopener" class="concern-thread__image-link">' +
                      '<img src="' +
                      escapeHtml(msg.image_url) +
                      '" alt="Attachment" class="concern-thread__image">' +
                      "</a>"
                    : "";
                return (
                    '<div class="concern-thread__message concern-thread__message--' +
                    escapeHtml(msg.author_role) +
                    '">' +
                    '<div class="concern-thread__bubble">' +
                    bodyHtml +
                    imageHtml +
                    "</div>" +
                    '<p class="concern-thread__meta">' +
                    escapeHtml(msg.author_name) +
                    (msg.created_at ? " · " + escapeHtml(formatTimestamp(msg.created_at)) : "") +
                    "</p>" +
                    "</div>"
                );
            })
            .join("");
        container.scrollTop = container.scrollHeight;
    }

    function renderSelect() {
        var select = document.getElementById("faculty-concern-select");
        if (!select) return;
        select.innerHTML = state.items
            .map(function (item) {
                var label =
                    item.student_name +
                    " — Q: " +
                    truncateStem(item.stem) +
                    (item.needs_faculty_reply ? " (pending)" : " (replied)");
                var selected = item.mistake_id === state.activeMistakeId ? " selected" : "";
                return (
                    '<option value="' +
                    item.mistake_id +
                    '"' +
                    selected +
                    ">" +
                    escapeHtml(label) +
                    "</option>"
                );
            })
            .join("");
    }

    function renderActive() {
        var item = activeItem();
        if (!item) return;

        var studentEl = document.getElementById("faculty-concern-student");
        var stemEl = document.getElementById("faculty-concern-stem");
        var userEl = document.getElementById("faculty-concern-user-answer");
        var correctEl = document.getElementById("faculty-concern-correct-answer");
        var aiEl = document.getElementById("faculty-concern-ai-feedback");
        var input = document.getElementById("faculty-concern-note-input");

        if (studentEl) {
            studentEl.textContent = item.student_name + " · " + item.student_email + " · " + item.topic;
        }
        if (stemEl) stemEl.textContent = item.stem;
        if (userEl) userEl.textContent = item.user_answer || "—";
        if (correctEl) correctEl.textContent = item.correct_answer || "—";
        if (aiEl) {
            aiEl.innerHTML = escapeHtml(item.ai_feedback || "No AI feedback generated yet.").replace(
                /\n/g,
                "<br>"
            );
        }
        if (input) input.value = "";
        renderThread(item.messages || []);
    }

    async function loadConcerns(preferredId) {
        var url = config().concernsUrl || "";
        if (preferredId) {
            url += (url.indexOf("?") >= 0 ? "&" : "?") + "mistake_id=" + encodeURIComponent(preferredId);
        }
        var resp = await fetch(url, {
            headers: { Accept: "application/json" },
            credentials: "same-origin",
        });
        if (!resp.ok) throw new Error("Could not load concerns.");
        var data = await resp.json();
        state.items = data.items || [];
        state.activeMistakeId = preferredId || data.active_mistake_id || (state.items[0] && state.items[0].mistake_id);
    }

    async function openConcern(mistakeId, screen) {
        openModal();
        setScreen(screen || "ai");
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
            renderSelect();
            renderActive();
            if (loading) loading.classList.add("hidden");
            if (content) content.classList.remove("hidden");
            state.loaded = true;
        } catch (err) {
            if (loading) loading.classList.add("hidden");
            if (errorEl) {
                errorEl.textContent = err.message || "Failed to load concerns.";
                errorEl.classList.remove("hidden");
            }
        }
    }

    async function saveNote() {
        var item = activeItem();
        var input = document.getElementById("faculty-concern-note-input");
        var btn = document.getElementById("faculty-concern-save-btn");
        if (!item || !input) return;
        var body = (input.value || "").trim();
        if (!body) {
            if (typeof showToast === "function") showToast("Enter a reply first.", "warning");
            return;
        }
        if (btn && window.ExamiQUI && window.ExamiQUI.setButtonLoading) {
            window.ExamiQUI.setButtonLoading(btn, true, "Sending…");
        }
        try {
            var fd = new FormData();
            fd.append("csrfmiddlewaretoken", config().csrfToken || "");
            fd.append("faculty_note", body);
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
            renderSelect();
            renderActive();
            updateListRowStatus(updated);
            if (typeof showToast === "function") showToast("Reply sent.", "success");
        } catch (err) {
            if (typeof showToast === "function") {
                showToast(err.message || "Could not send reply.", "error");
            }
        } finally {
            if (btn && window.ExamiQUI && window.ExamiQUI.setButtonLoading) {
                window.ExamiQUI.setButtonLoading(btn, false);
            }
        }
    }

    function updateListRowStatus(item) {
        var btn = document.querySelector('.open-concern-btn[data-mistake-id="' + item.mistake_id + '"]');
        if (!btn) return;
        var row = btn.closest("tr");
        if (!row) return;
        var statusCell = row.querySelector("[data-concern-status]");
        if (!statusCell) return;
        if (item.needs_faculty_reply) {
            statusCell.innerHTML =
                '<span class="inline-flex items-center px-2 py-0.5 rounded-lg text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-200">Pending</span>';
        } else {
            statusCell.innerHTML =
                '<span class="inline-flex items-center px-2 py-0.5 rounded-lg text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">Replied</span>';
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
        var select = document.getElementById("faculty-concern-select");
        if (select) {
            select.addEventListener("change", function () {
                state.activeMistakeId = parseInt(select.value, 10);
                renderActive();
            });
        }
        var saveBtn = document.getElementById("faculty-concern-save-btn");
        if (saveBtn) saveBtn.addEventListener("click", saveNote);

        var params = new URLSearchParams(window.location.search);
        var mid = params.get("mistake_id");
        if (mid && document.getElementById("faculty-concern-modal")) {
            openConcern(parseInt(mid, 10), "conversation");
        }
    });
})();
