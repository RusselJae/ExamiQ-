/**
 * Global Chat inbox modal — faculty concern threads.
 * Students use the AI Tutor modal from the navbar instead.
 */
(function () {
    "use strict";

    var state = {
        items: [],
        activeMistakeId: null,
        loaded: false,
        sending: false,
        filter: "",
    };

    function config() {
        return window.ExamiQChat || {};
    }

    function isFaculty() {
        return config().role === "professor";
    }

    function truncatePreview(text, max) {
        var value = (text || "").trim();
        if (value.length <= max) return value;
        return value.slice(0, Math.max(0, max - 1)) + "…";
    }

    function escapeHtml(text) {
        var div = document.createElement("div");
        div.textContent = text || "";
        return div.innerHTML;
    }

    function noteUrl(mistakeId) {
        return (config().noteUrlBase || "").replace("/0/", "/" + mistakeId + "/");
    }

    function concernUrl(answerId) {
        return (config().concernUrlTemplate || "").replace("/0/", "/" + answerId + "/");
    }

    function activeItem() {
        return state.items.find(function (item) {
            return item.mistake_id === state.activeMistakeId;
        });
    }

    function formatListDate(iso) {
        if (!iso) return "";
        var d = new Date(iso);
        if (isNaN(d.getTime())) return "";
        return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    }

    function formatTime(iso) {
        if (!iso) return "";
        var d = new Date(iso);
        if (isNaN(d.getTime())) return "";
        return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    }

    function avatarHtml(url, initials, extraClass) {
        var cls = "examiq-chat-avatar" + (extraClass ? " " + extraClass : "");
        if (url) {
            return (
                '<img class="' +
                cls +
                '" src="' +
                escapeHtml(url) +
                '" alt="" width="36" height="36">'
            );
        }
        return (
            '<div class="' +
            cls +
            ' examiq-chat-avatar--initials" aria-hidden="true">' +
            escapeHtml(initials || "?") +
            "</div>"
        );
    }

    function openModal() {
        var modal = document.getElementById("examiq-chat-modal");
        if (modal) modal.classList.remove("hidden");
        document.documentElement.classList.add("examiq-chat-open");
    }

    function closeModal() {
        var modal = document.getElementById("examiq-chat-modal");
        if (modal) modal.classList.add("hidden");
        document.documentElement.classList.remove("examiq-chat-open");
    }

    function filteredItems() {
        var q = (state.filter || "").trim().toLowerCase();
        if (!q) return state.items.slice();
        return state.items.filter(function (item) {
            var hay = [
                item.student_name,
                item.student_email,
                item.subject_code,
                item.preview,
                item.stem,
                item.topic,
            ]
                .join(" ")
                .toLowerCase();
            return hay.indexOf(q) !== -1;
        });
    }

    function renderList() {
        var list = document.getElementById("examiq-chat-list");
        var empty = document.getElementById("examiq-chat-list-empty");
        if (!list) return;
        var items = filteredItems();
        if (!items.length) {
            list.innerHTML = "";
            if (empty) empty.classList.remove("hidden");
            return;
        }
        if (empty) empty.classList.add("hidden");
        list.innerHTML = items
            .map(function (item) {
                var active =
                    item.mistake_id === state.activeMistakeId
                        ? " examiq-chat-item--active"
                        : "";
                var badge = item.needs_faculty_reply
                    ? '<span class="examiq-chat-item__dot" title="Needs reply"></span>'
                    : "";
                return (
                    '<button type="button" class="examiq-chat-item' +
                    active +
                    '" data-mistake-id="' +
                    item.mistake_id +
                    '" role="option" aria-selected="' +
                    (item.mistake_id === state.activeMistakeId ? "true" : "false") +
                    '">' +
                    avatarHtml(
                        item.student_avatar_url,
                        item.student_initials || "?",
                        "examiq-chat-item__avatar"
                    ) +
                    '<div class="examiq-chat-item__body">' +
                    '<div class="examiq-chat-item__row">' +
                    '<span class="examiq-chat-item__name">' +
                    escapeHtml(item.student_name || "Student") +
                    badge +
                    "</span>" +
                    '<span class="examiq-chat-item__date">' +
                    escapeHtml(formatListDate(item.last_message_at || item.occurred_at)) +
                    "</span></div>" +
                    '<p class="examiq-chat-item__preview">' +
                    escapeHtml(item.preview || "") +
                    "</p>" +
                    "</div></button>"
                );
            })
            .join("");
    }

    function setPeerAvatar(el, url, initials) {
        if (!el) return;
        if (url) {
            el.className = "examiq-chat-modal__avatar examiq-chat-modal__avatar--photo";
            el.innerHTML =
                '<img src="' + escapeHtml(url) + '" alt="" width="40" height="40">';
            return;
        }
        el.className = "examiq-chat-modal__avatar";
        el.textContent = initials || "?";
    }

    function renderThread() {
        var thread = document.getElementById("examiq-chat-thread");
        var avatar = document.getElementById("examiq-chat-peer-avatar");
        var nameEl = document.getElementById("examiq-chat-peer-name");
        var metaEl = document.getElementById("examiq-chat-peer-meta");
        var input = document.getElementById("examiq-chat-input");
        var send = document.getElementById("examiq-chat-send");
        var item = activeItem();
        if (!thread) return;

        if (!item) {
            thread.innerHTML =
                '<p class="examiq-chat-modal__thread-empty">Select a conversation to start messaging.</p>';
            setPeerAvatar(avatar, "", "?");
            if (nameEl) nameEl.textContent = "Select a conversation";
            if (metaEl) metaEl.textContent = "";
            if (input) {
                input.value = "";
                input.disabled = true;
            }
            if (send) send.disabled = true;
            return;
        }

        setPeerAvatar(avatar, item.student_avatar_url, item.student_initials || "?");
        if (nameEl) nameEl.textContent = item.student_name || "Student";
        if (metaEl) metaEl.textContent = item.student_email || "";
        if (input) input.disabled = false;
        if (send) send.disabled = false;

        var msgs = item.messages || [];
        var parts = [];
        if (item.stem) {
            parts.push(
                '<div class="examiq-chat-question">' +
                    '<p class="examiq-chat-question__label">Question</p>' +
                    '<p class="examiq-chat-question__stem">' +
                    escapeHtml(item.stem) +
                    "</p></div>"
            );
        }

        if (!msgs.length) {
            parts.push(
                '<p class="examiq-chat-modal__thread-empty">No messages yet. Send the first reply.</p>'
            );
            thread.innerHTML = parts.join("");
            return;
        }

        var selfCfg = config();
        parts = parts.concat(
            msgs.map(function (msg) {
                var isStudent = msg.author_role === "student";
                // Student bubbles left, faculty bubbles right.
                var side = isStudent ? "in" : "out";
                var avatarUrl = isStudent
                    ? msg.author_avatar_url || item.student_avatar_url || ""
                    : msg.author_avatar_url || selfCfg.selfAvatarUrl || "";
                var initials = isStudent
                    ? msg.author_initials || item.student_initials || "?"
                    : msg.author_initials || selfCfg.selfInitials || "FA";
                var body = msg.body
                    ? '<p class="examiq-chat-bubble__text">' +
                      escapeHtml(msg.body).replace(/\n/g, "<br>") +
                      "</p>"
                    : "";
                var image = msg.image_url
                    ? '<a class="examiq-chat-bubble__image" href="' +
                      escapeHtml(msg.image_url) +
                      '" target="_blank" rel="noopener"><img src="' +
                      escapeHtml(msg.image_url) +
                      '" alt="Attachment"></a>'
                    : "";
                return (
                    '<div class="examiq-chat-msg examiq-chat-msg--' +
                    side +
                    '">' +
                    '<div class="examiq-chat-msg__row examiq-chat-msg__row--' +
                    side +
                    '">' +
                    (isStudent
                        ? avatarHtml(avatarUrl, initials, "examiq-chat-msg__avatar")
                        : "") +
                    '<div class="examiq-chat-bubble examiq-chat-bubble--' +
                    side +
                    '">' +
                    body +
                    image +
                    "</div>" +
                    (!isStudent
                        ? avatarHtml(avatarUrl, initials, "examiq-chat-msg__avatar")
                        : "") +
                    "</div>" +
                    '<span class="examiq-chat-msg__time">' +
                    escapeHtml(formatTime(msg.created_at)) +
                    "</span></div>"
                );
            })
        );
        thread.innerHTML = parts.join("");
        thread.scrollTop = thread.scrollHeight;
    }

    async function loadItems(preferredId) {
        var url = config().concernsUrl;
        if (!url) return;
        var sep = url.indexOf("?") >= 0 ? "&" : "?";
        if (preferredId) url += sep + "mistake_id=" + encodeURIComponent(preferredId);
        var res = await fetch(url, {
            credentials: "same-origin",
            headers: { Accept: "application/json" },
        });
        if (!res.ok) throw new Error("Could not load conversations");
        var data = await res.json();
        state.items = data.items || [];
        state.activeMistakeId =
            preferredId ||
            data.active_mistake_id ||
            (state.items[0] && state.items[0].mistake_id) ||
            null;
        state.loaded = true;
        renderList();
        renderThread();
    }

    async function sendMessage(event) {
        event.preventDefault();
        if (state.sending) return;
        var item = activeItem();
        var input = document.getElementById("examiq-chat-input");
        if (!item || !input) return;
        var body = (input.value || "").trim();
        if (!body) return;

        var url = isFaculty()
            ? noteUrl(item.mistake_id)
            : concernUrl(item.answer_id);
        if (!url) return;

        state.sending = true;
        var send = document.getElementById("examiq-chat-send");
        if (send) send.disabled = true;

        try {
            var fd = new FormData();
            if (isFaculty()) {
                fd.append("faculty_note", body);
                fd.append("body", body);
            } else {
                fd.append("body", body);
            }
            var res = await fetch(url, {
                method: "POST",
                headers: {
                    "X-CSRFToken": config().csrfToken || "",
                    "X-Requested-With": "XMLHttpRequest",
                    Accept: "application/json",
                },
                body: fd,
                credentials: "same-origin",
            });
            var data = await res.json().catch(function () {
                return {};
            });
            if (!res.ok || data.ok === false) {
                throw new Error(data.error || "Could not send message");
            }
            input.value = "";
            await loadItems(item.mistake_id);
        } catch (err) {
            if (typeof showToast === "function") {
                showToast(err.message || "Could not send message", "error");
            }
        } finally {
            state.sending = false;
            if (send) send.disabled = false;
            if (input) input.focus();
        }
    }

    async function openChat(options) {
        options = options || {};
        openModal();
        try {
            await loadItems(options.mistakeId || null);
        } catch (err) {
            var thread = document.getElementById("examiq-chat-thread");
            if (thread) {
                thread.innerHTML =
                    '<p class="examiq-chat-modal__thread-empty">Could not load conversations.</p>';
            }
        }
    }

    function bind() {
        document.querySelectorAll("[data-open-chat-modal]").forEach(function (el) {
            el.addEventListener("click", function (event) {
                event.preventDefault();
                openChat();
            });
        });
        document.querySelectorAll("[data-dismiss-chat-modal]").forEach(function (el) {
            el.addEventListener("click", closeModal);
        });
        var list = document.getElementById("examiq-chat-list");
        if (list) {
            list.addEventListener("click", function (event) {
                var btn = event.target.closest("[data-mistake-id]");
                if (!btn) return;
                state.activeMistakeId = parseInt(btn.getAttribute("data-mistake-id"), 10);
                renderList();
                renderThread();
            });
        }
        var search = document.getElementById("examiq-chat-search");
        if (search) {
            search.addEventListener("input", function () {
                state.filter = search.value || "";
                renderList();
            });
        }
        var form = document.getElementById("examiq-chat-form");
        if (form) form.addEventListener("submit", sendMessage);
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") closeModal();
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (!document.getElementById("examiq-chat-modal")) return;
        bind();
        window.ExamiQChat = window.ExamiQChat || {};
        window.ExamiQChat.open = openChat;
        window.ExamiQChat.close = closeModal;

        var params = new URLSearchParams(window.location.search);
        if (params.get("open_chat") === "1" || params.get("mistake_id")) {
            openChat({ mistakeId: params.get("mistake_id") });
        }
    });
})();
