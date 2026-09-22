/**
 * Global Chat inbox modal — student–faculty threads, plus faculty–faculty DMs.
 */
(function () {
    "use strict";

    var state = {
        items: [],
        activeConversationId: null,
        activePeerId: null,
        loaded: false,
        sending: false,
        filter: "",
        tab: "students",
    };

    function config() {
        return window.ExamiQChat || {};
    }

    function isFaculty() {
        return config().role === "professor";
    }

    function isFacultyTab() {
        return isFaculty() && state.tab === "faculty";
    }

    function escapeHtml(text) {
        var div = document.createElement("div");
        div.textContent = text || "";
        return div.innerHTML;
    }

    function messageUrl(conversationId) {
        if (isFacultyTab()) {
            if (conversationId) {
                return (config().facultyNoteUrlBase || "").replace(
                    "/0/",
                    "/" + conversationId + "/"
                );
            }
            return config().facultyMessageUrl || "";
        }
        if (isFaculty()) {
            return (config().noteUrlBase || "").replace("/0/", "/" + conversationId + "/");
        }
        return config().messageUrl || "";
    }

    function conversationsUrl() {
        if (isFacultyTab()) {
            return config().facultyConversationsUrl || "";
        }
        return config().concernsUrl || config().conversationsUrl || "";
    }

    function itemKey(item) {
        if (item.conversation_id) return "c:" + item.conversation_id;
        if (item.peer_id) return "p:" + item.peer_id;
        return "";
    }

    function activeItem() {
        return state.items.find(function (item) {
            if (state.activeConversationId && item.conversation_id === state.activeConversationId) {
                return true;
            }
            if (
                !state.activeConversationId &&
                state.activePeerId &&
                item.peer_id === state.activePeerId &&
                !item.conversation_id
            ) {
                return true;
            }
            return false;
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
        if (isFacultyTab() || item.thread_type === "faculty") {
            return item.peer_name || item.student_name || "Faculty";
        }
        if (isFaculty()) {
            return item.student_name || "Student";
        }
        return item.peer_name || "Faculty";
    }

    function listItemAvatar(item) {
        if (isFacultyTab() || item.thread_type === "faculty") {
            return {
                url: item.peer_avatar_url || item.student_avatar_url,
                initials: item.peer_initials || item.student_initials || "?",
            };
        }
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
                item.peer_email,
                item.preview,
            ]
                .join(" ")
                .toLowerCase();
            return hay.indexOf(q) !== -1;
        });
    }

    function isActiveListItem(item) {
        if (item.conversation_id && item.conversation_id === state.activeConversationId) {
            return true;
        }
        if (
            !item.conversation_id &&
            item.peer_id &&
            item.peer_id === state.activePeerId &&
            !state.activeConversationId
        ) {
            return true;
        }
        return false;
    }

    function renderList() {
        var list = document.getElementById("examiq-chat-list");
        var empty = document.getElementById("examiq-chat-list-empty");
        if (!list) return;
        var items = filteredItems();
        if (!items.length) {
            list.innerHTML = "";
            if (empty) {
                empty.textContent = isFacultyTab()
                    ? "No faculty colleagues found."
                    : "No conversations yet.";
                empty.classList.remove("hidden");
            }
            return;
        }
        if (empty) empty.classList.add("hidden");
        list.innerHTML = items
            .map(function (item) {
                var active = isActiveListItem(item) ? " examiq-chat-item--active" : "";
                var badge = "";
                if (isFaculty() && item.needs_faculty_reply) {
                    badge = '<span class="examiq-chat-item__dot" title="Needs reply"></span>';
                } else if (!isFaculty() && item.needs_student_attention) {
                    badge = '<span class="examiq-chat-item__dot" title="New reply"></span>';
                }
                var av = listItemAvatar(item);
                var attrs =
                    ' data-item-key="' +
                    escapeHtml(itemKey(item)) +
                    '"' +
                    (item.conversation_id
                        ? ' data-conversation-id="' + item.conversation_id + '"'
                        : "") +
                    (item.peer_id ? ' data-peer-id="' + item.peer_id + '"' : "");
                return (
                    '<button type="button" class="examiq-chat-item' +
                    active +
                    '"' +
                    attrs +
                    ' role="option" aria-selected="' +
                    (isActiveListItem(item) ? "true" : "false") +
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
        var selfId = config().selfUserId;
        if (selfId && msg.author_id) {
            return msg.author_id === selfId ? "out" : "in";
        }
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

    function updateTabUi() {
        document.querySelectorAll("[data-chat-tab]").forEach(function (btn) {
            var active = btn.getAttribute("data-chat-tab") === state.tab;
            btn.classList.toggle("examiq-chat-modal__tab--active", active);
            btn.setAttribute("aria-selected", active ? "true" : "false");
        });
        var search = document.getElementById("examiq-chat-search");
        if (search) {
            search.placeholder = isFacultyTab() ? "Search faculty…" : "Search students…";
        }
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
            metaEl.textContent = isFaculty()
                ? item.peer_email || item.student_email || ""
                : "";
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
        var url = conversationsUrl();
        if (!url) return;
        var sep = url.indexOf("?") >= 0 ? "&" : "?";
        if (preferredId) {
            url += sep + "conversation_id=" + encodeURIComponent(preferredId);
            sep = "&";
        }
        if (studentId && !isFacultyTab()) {
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
            null;
        state.activePeerId = null;
        if (!state.activeConversationId) {
            var first = state.items[0];
            if (first) {
                if (first.conversation_id) {
                    state.activeConversationId = first.conversation_id;
                } else if (first.peer_id) {
                    state.activePeerId = first.peer_id;
                }
            }
        }
        state.loaded = true;
        renderList();
        renderThread();
    }

    async function setTab(tab, options) {
        options = options || {};
        state.tab = tab === "faculty" ? "faculty" : "students";
        state.filter = "";
        state.activeConversationId = options.conversationId || null;
        state.activePeerId = options.peerId || null;
        var search = document.getElementById("examiq-chat-search");
        if (search) search.value = "";
        updateTabUi();
        await loadItems(state.activeConversationId, options.studentId || null);
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
        var peerId = item ? item.peer_id : state.activePeerId;

        if (isFaculty() && !isFacultyTab() && !conversationId) return;
        if (isFacultyTab() && !conversationId && !peerId) return;

        var url = messageUrl(conversationId);
        if (!url) return;

        state.sending = true;
        var send = document.getElementById("examiq-chat-send");
        if (send) send.disabled = true;

        try {
            var fd = new FormData();
            fd.append("body", body);
            if (imageFile) fd.append("image", imageFile);
            if (isFacultyTab() && !conversationId && peerId) {
                fd.append("peer_id", String(peerId));
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
            if (imageInput) {
                imageInput.value = "";
                var imageName = document.getElementById("examiq-chat-image-name");
                if (imageName) imageName.classList.add("hidden");
            }
            if (data.item) {
                var newKey = itemKey(data.item);
                var idx = state.items.findIndex(function (i) {
                    return itemKey(i) === newKey || i.peer_id === data.item.peer_id;
                });
                if (idx >= 0) {
                    state.items[idx] = data.item;
                } else {
                    state.items.unshift(data.item);
                }
                // Drop placeholder peer rows once a real thread exists.
                if (data.item.conversation_id && data.item.peer_id) {
                    state.items = state.items.filter(function (i) {
                        return !(
                            !i.conversation_id &&
                            i.peer_id === data.item.peer_id
                        );
                    });
                }
                state.activeConversationId = data.item.conversation_id;
                state.activePeerId = null;
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
            if (options.tab === "faculty" || options.chatTab === "faculty") {
                await setTab("faculty", {
                    conversationId: options.conversationId || null,
                    peerId: options.peerId || null,
                });
            } else {
                await setTab("students", {
                    conversationId: options.conversationId || null,
                    studentId: options.studentId || null,
                });
            }
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
                openChat({ studentId: studentId, tab: "students" });
            });
        });
        document.querySelectorAll("[data-dismiss-chat-modal]").forEach(function (el) {
            el.addEventListener("click", closeModal);
        });
        document.querySelectorAll("[data-chat-tab]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var tab = btn.getAttribute("data-chat-tab") || "students";
                setTab(tab).catch(function () {});
            });
        });
        var list = document.getElementById("examiq-chat-list");
        if (list) {
            list.addEventListener("click", function (event) {
                var btn = event.target.closest("[data-item-key]");
                if (!btn) return;
                var convId = btn.getAttribute("data-conversation-id");
                var peerId = btn.getAttribute("data-peer-id");
                state.activeConversationId = convId ? parseInt(convId, 10) : null;
                state.activePeerId = peerId && !convId ? parseInt(peerId, 10) : null;
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
        updateTabUi();
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
                tab: params.get("chat_tab") || "students",
            });
        }
    });
})();
