/**
 * Global Chat inbox modal — one thread per student with assigned faculty.
 */
(function () {
    "use strict";

    var state = {
        items: [],
        activeConversationId: null,
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

    function escapeHtml(text) {
        var div = document.createElement("div");
        div.textContent = text || "";
        return div.innerHTML;
    }

    function messageUrl(conversationId) {
        if (isFaculty()) {
            return (config().noteUrlBase || "").replace("/0/", "/" + conversationId + "/");
        }
        return config().messageUrl || "";
    }

    function activeItem() {
        return state.items.find(function (item) {
            return item.conversation_id === state.activeConversationId;
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

    function listItemName(item) {
        if (isFaculty()) {
            return item.student_name || "Student";
        }
        return item.peer_name || "Faculty";
    }

    function listItemAvatar(item) {
        if (isFaculty()) {
            return {
                url: item.student_avatar_url,
                initials: item.student_initials || "?",
            };
        }
        return {
            url: item.peer_avatar_url,
            initials: item.peer_initials || "FA",
        };
    }

    function filteredItems() {
        var q = (state.filter || "").trim().toLowerCase();
        if (!q) return state.items.slice();
        return state.items.filter(function (item) {
            var hay = [
                item.student_name,
                item.student_email,
                item.peer_name,
                item.preview,
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
                    item.conversation_id === state.activeConversationId
                        ? " examiq-chat-item--active"
                        : "";
                var badge = "";
                if (isFaculty() && item.needs_faculty_reply) {
                    badge = '<span class="examiq-chat-item__dot" title="Needs reply"></span>';
                } else if (!isFaculty() && item.needs_student_attention) {
                    badge = '<span class="examiq-chat-item__dot" title="New reply"></span>';
                }
                var av = listItemAvatar(item);
                return (
                    '<button type="button" class="examiq-chat-item' +
                    active +
                    '" data-conversation-id="' +
                    item.conversation_id +
                    '" role="option" aria-selected="' +
                    (item.conversation_id === state.activeConversationId
                        ? "true"
                        : "false") +
                    '">' +
                    avatarHtml(av.url, av.initials, "examiq-chat-item__avatar") +
                    '<div class="examiq-chat-item__body">' +
                    '<div class="examiq-chat-item__row">' +
                    '<span class="examiq-chat-item__name">' +
                    escapeHtml(listItemName(item)) +
                    badge +
                    "</span>" +
                    '<span class="examiq-chat-item__date">' +
                    escapeHtml(formatListDate(item.last_message_at)) +
                    "</span></div>" +
                    '<p class="examiq-chat-item__preview">' +
                    escapeHtml(item.preview || "") +
                    "</p>" +
                    "</div></button>"
                );
            })
            .join("");
    }

    function dedupeMessages(msgs) {
        var seen = {};
        return (msgs || []).filter(function (msg) {
            var key = msg.id
                ? "id:" + msg.id
                : [
                      msg.created_at || "",
                      msg.author_role || "",
                      msg.body || "",
                      msg.image_url || "",
                  ].join("|");
            if (seen[key]) return false;
            seen[key] = true;
            return true;
        });
    }

    function messageSide(msg) {
        var isStudentMsg = msg.author_role === "student";
        var isOwnMessage = isFaculty() ? !isStudentMsg : isStudentMsg;
        return isOwnMessage ? "out" : "in";
    }

    function messageAvatar(msg, item) {
        var isStudent = msg.author_role === "student";
        var url = msg.author_avatar_url || "";
        var initials = msg.author_initials || "?";
        if (isStudent) {
            if (!url) url = item.student_avatar_url || "";
            if (!initials || initials === "?") {
                initials = item.student_initials || initials;
            }
        } else if (!url) {
            url = item.peer_avatar_url || "";
            initials = msg.author_initials || item.peer_initials || "FA";
        }
        return { url: url, initials: initials };
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
            if (nameEl) nameEl.textContent = isFaculty() ? "Select a conversation" : "Faculty";
            if (metaEl) metaEl.textContent = "";
            if (input) {
                input.value = "";
                input.disabled = !isFaculty() ? false : true;
            }
            if (send) send.disabled = !isFaculty() ? false : true;
            return;
        }

        var peerAv = listItemAvatar(item);
        setPeerAvatar(avatar, peerAv.url, peerAv.initials);
        if (nameEl) nameEl.textContent = listItemName(item);
        if (metaEl) {
            metaEl.textContent = isFaculty() ? item.student_email || "" : "";
        }
        if (input) input.disabled = false;
        if (send) send.disabled = false;

        var msgs = dedupeMessages(item.messages || []);
        if (!msgs.length) {
            thread.innerHTML =
                '<p class="examiq-chat-modal__thread-empty">No messages yet. Send the first message.</p>';
            return;
        }

        thread.innerHTML = msgs
            .map(function (msg) {
                var side = messageSide(msg);
                var av = messageAvatar(msg, item);
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
                var avatarLeft = side === "in";
                return (
                    '<div class="examiq-chat-msg examiq-chat-msg--' +
                    side +
                    '">' +
                    '<div class="examiq-chat-msg__row examiq-chat-msg__row--' +
                    side +
                    '">' +
                    (avatarLeft
                        ? avatarHtml(av.url, av.initials, "examiq-chat-msg__avatar")
                        : "") +
                    '<div class="examiq-chat-bubble examiq-chat-bubble--' +
                    side +
                    '">' +
                    body +
                    image +
                    "</div>" +
                    (!avatarLeft
                        ? avatarHtml(av.url, av.initials, "examiq-chat-msg__avatar")
                        : "") +
                    "</div>" +
                    '<span class="examiq-chat-msg__time">' +
                    escapeHtml(formatTime(msg.created_at)) +
                    "</span></div>"
                );
            })
            .join("");
        thread.scrollTop = thread.scrollHeight;
    }

    async function loadItems(preferredId, studentId) {
        var url = config().concernsUrl || config().conversationsUrl;
        if (!url) return;
        var sep = url.indexOf("?") >= 0 ? "&" : "?";
        if (preferredId) {
            url += sep + "conversation_id=" + encodeURIComponent(preferredId);
            sep = "&";
        }
        if (studentId) {
            url += sep + "student_id=" + encodeURIComponent(studentId);
        }
        var res = await fetch(url, {
            credentials: "same-origin",
            headers: { Accept: "application/json" },
        });
        if (!res.ok) throw new Error("Could not load conversations");
        var data = await res.json();
        state.items = data.items || [];
        state.activeConversationId =
            preferredId ||
            data.active_conversation_id ||
            (state.items[0] && state.items[0].conversation_id) ||
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
        var imageInput = document.getElementById("examiq-chat-image");
        if (!input) return;
        var body = (input.value || "").trim();
        var imageFile = imageInput && imageInput.files && imageInput.files[0];
        if (!body && !imageFile) return;

        var conversationId = item ? item.conversation_id : state.activeConversationId;
        if (isFaculty() && !conversationId) return;

        var url = isFaculty()
            ? messageUrl(conversationId)
            : config().messageUrl;
        if (!url) return;

        state.sending = true;
        var send = document.getElementById("examiq-chat-send");
        if (send) send.disabled = true;

        try {
            var fd = new FormData();
            fd.append("body", body);
            if (imageFile) fd.append("image", imageFile);
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
            if (imageInput) {
                imageInput.value = "";
                var imageName = document.getElementById("examiq-chat-image-name");
                if (imageName) imageName.classList.add("hidden");
            }
            if (data.item) {
                var idx = state.items.findIndex(function (i) {
                    return i.conversation_id === data.item.conversation_id;
                });
                if (idx >= 0) {
                    state.items[idx] = data.item;
                } else {
                    state.items = [data.item];
                }
                state.activeConversationId = data.item.conversation_id;
                renderList();
                renderThread();
            } else {
                await loadItems(conversationId);
            }
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
            await loadItems(
                options.conversationId || null,
                options.studentId || null
            );
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
        document.querySelectorAll("[data-open-student-chat]").forEach(function (el) {
            el.addEventListener("click", function (event) {
                event.preventDefault();
                var studentId = el.getAttribute("data-student-id");
                openChat({ studentId: studentId });
            });
        });
        document.querySelectorAll("[data-dismiss-chat-modal]").forEach(function (el) {
            el.addEventListener("click", closeModal);
        });
        var list = document.getElementById("examiq-chat-list");
        if (list) {
            list.addEventListener("click", function (event) {
                var btn = event.target.closest("[data-conversation-id]");
                if (!btn) return;
                state.activeConversationId = parseInt(
                    btn.getAttribute("data-conversation-id"),
                    10
                );
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
        if (form && !form.dataset.chatBound) {
            form.dataset.chatBound = "1";
            form.addEventListener("submit", sendMessage);
        }
        var imageInput = document.getElementById("examiq-chat-image");
        var imageName = document.getElementById("examiq-chat-image-name");
        if (imageInput && imageName) {
            imageInput.addEventListener("change", function () {
                if (imageInput.files && imageInput.files[0]) {
                    imageName.textContent = imageInput.files[0].name;
                    imageName.classList.remove("hidden");
                } else {
                    imageName.classList.add("hidden");
                }
            });
        }
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
        if (
            params.get("open_chat") === "1" ||
            params.get("conversation_id") ||
            params.get("student_id")
        ) {
            openChat({
                conversationId: params.get("conversation_id"),
                studentId: params.get("student_id"),
            });
        }
    });
})();
