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
        messages: [],
        activeAnswerId: null,
        sending: false,
        loaded: false,
        enriching: {},
        screen: "solution",
        preferredScreen: "solution",
        reviewMode: false,
        includeAll: false,
    };

    function escapeHtml(text) {
        var div = document.createElement("div");
        div.textContent = text || "";
        return div.innerHTML;
    }

    function katexRender(el) {
        if (typeof window.renderMathInElement !== "undefined" && el) {
            window.renderMathInElement(el, {
                delimiters: [
                    { left: "$$", right: "$$", display: true },
                    { left: "$", right: "$", display: false },
                ],
            });
        }
    }

    function getConfig() {
        return window.ExamiQTutor || {};
    }

    function markAnswerNotificationsRead(answerId) {
        var config = getConfig();
        var url = config.markNotificationsUrl;
        if (!url || !answerId) return;
        var fd = new FormData();
        fd.append("answer_id", String(answerId));
        fetch(url, {
            method: "POST",
            headers: { "X-CSRFToken": config.csrfToken || "" },
            body: fd,
            credentials: "same-origin",
        }).catch(function () {});
    }

    function historyUrlForAnswer(answerId) {
        var config = getConfig();
        if (!config.historyUrl) return "";
        if (!answerId) return config.historyUrl;
        var sep = config.historyUrl.indexOf("?") >= 0 ? "&" : "?";
        return config.historyUrl + sep + "answer_id=" + encodeURIComponent(answerId);
    }

    function feedbackUrlForAnswer(answerId) {
        var config = getConfig();
        if (!config.feedbackUrl) return "";
        var sep = config.feedbackUrl.indexOf("?") >= 0 ? "&" : "?";
        return config.feedbackUrl + sep + "answer_id=" + encodeURIComponent(answerId);
    }

    function concernUrlForAnswer(answerId) {
        var config = getConfig();
        if (config.concernUrlTemplate && answerId) {
            return config.concernUrlTemplate.replace("{pk}", String(answerId));
        }
        if (config.concernUrl) return config.concernUrl;
        return "";
    }

    function applySessionUrls(sessionId) {
        var config = getConfig();
        var templates = config.urlTemplates || {};
        if (!sessionId || !templates.history) return;
        config.historyUrl = templates.history.replace("{pk}", String(sessionId));
        config.chatUrl = templates.chat.replace("{pk}", String(sessionId));
        config.feedbackUrl = templates.feedback.replace("{pk}", String(sessionId));
        if (templates.concern) {
            config.concernUrlTemplate = templates.concern;
        }
    }

    function openModal() {
        var modal = document.getElementById("ai-tutor-modal");
        if (!modal) return;
        modal.classList.remove("hidden");
        document.body.classList.add("ai-tutor-modal-open");
    }

    function closeModal() {
        var modal = document.getElementById("ai-tutor-modal");
        if (!modal) return;
        modal.classList.add("hidden");
        document.body.classList.remove("ai-tutor-modal-open");
    }

    function showError(message) {
        var loading = document.getElementById("ai-tutor-loading");
        var content = document.getElementById("ai-tutor-content");
        var errorEl = document.getElementById("ai-tutor-error");
        if (loading) loading.classList.add("hidden");
        if (content) content.classList.add("hidden");
        if (errorEl) {
            errorEl.textContent = message;
            errorEl.classList.remove("hidden");
        }
    }

    function truncateStem(stem) {
        if (!stem) return "Question";
        return stem.length > 72 ? stem.slice(0, 69) + "…" : stem;
    }

    function formatTimestamp(iso) {
        if (!iso) return "";
        try {
            return new Date(iso).toLocaleString();
        } catch (e) {
            return iso;
        }
    }

    async function loadHistoryForAnswer(answerId) {
        var url = historyUrlForAnswer(answerId);
        if (!url) return;
        var resp = await fetch(url, {
            headers: { Accept: "application/json" },
            credentials: "same-origin",
        });
        if (!resp.ok) throw new Error("history failed");
        var data = await resp.json();
        state.messages = data.messages || [];
        if (data.items && data.items.length) {
            state.items = data.items;
        }
        if (data.active_answer_id) {
            state.activeAnswerId = data.active_answer_id;
        } else if (answerId) {
            state.activeAnswerId = answerId;
        }
    }

    function mergeFeedbackItem(fbItem) {
        var existing = state.items.find(function (item) {
            return item.answer_id === fbItem.answer_id;
        });
        if (existing) {
            existing.feedback = fbItem.feedback;
            existing.needs_ai = false;
        } else {
            fbItem.needs_ai = false;
            state.items.push(fbItem);
        }
    }

    async function enrichAnswerFeedback(answerId) {
        var item = state.items.find(function (entry) {
            return entry.answer_id === answerId;
        });
        if (!item || !item.needs_ai || state.enriching[answerId]) {
            return;
        }
        state.enriching[answerId] = true;
        renderFeedbackPanel();
        try {
            var resp = await fetch(feedbackUrlForAnswer(answerId), {
                method: "POST",
                headers: {
                    "X-CSRFToken": getConfig().csrfToken,
                    Accept: "application/json",
                },
                credentials: "same-origin",
            });
            if (!resp.ok) throw new Error("feedback failed");
            var data = await resp.json();
            if (data.items && data.items.length) {
                data.items.forEach(mergeFeedbackItem);
            }
        } catch (err) {
            item.needs_ai = false;
            if (typeof showToast === "function") {
                showToast("Could not enrich AI feedback for this question. Showing available explanation.", "warning");
            }
        } finally {
            delete state.enriching[answerId];
            if (state.activeAnswerId === answerId) {
                renderFeedbackPanel();
            }
            renderQuestionSelect();
        }
    }

    function enrichPendingFeedback() {
        var queue = state.items.filter(function (item) {
            return item.needs_ai;
        });
        queue.sort(function (a, b) {
            if (a.answer_id === state.activeAnswerId) return -1;
            if (b.answer_id === state.activeAnswerId) return 1;
            return 0;
        });
        var chain = Promise.resolve();
        queue.forEach(function (item) {
            chain = chain.then(function () {
                return enrichAnswerFeedback(item.answer_id);
            });
        });
        return chain;
    }

    function reviewItems() {
        if (state.includeAll || state.reviewMode) {
            return state.items.slice();
        }
        var items = state.items.filter(function (item) {
            return !item.is_correct;
        });
        return items.length ? items : state.items;
    }

    async function selectAnswer(answerId) {
        state.activeAnswerId = answerId;
        try {
            await loadHistoryForAnswer(answerId);
            renderQuestionSelect();
            renderFeedbackPanel();
            renderMessages();
            if (!state.reviewMode) {
                enrichAnswerFeedback(answerId);
            }
        } catch (err) {
            if (typeof showToast === "function") {
                showToast("Could not load saved conversation for this question.", "error");
            }
        }
    }

    function renderQuestionSelect() {
        var select = document.getElementById("ai-tutor-question-select");
        var countEl = document.getElementById("ai-tutor-review-count");
        if (!select) return;

        var items = reviewItems();
        if (countEl) {
            countEl.textContent = "Reviewing " + items.length + " item" + (items.length === 1 ? "" : "s");
        }

        select.innerHTML = items
            .map(function (item) {
                var absoluteIndex = state.items.findIndex(function (entry) {
                    return entry.answer_id === item.answer_id;
                });
                var qNum = absoluteIndex >= 0 ? absoluteIndex + 1 : 1;
                var pending =
                    !state.reviewMode &&
                    (item.needs_ai || state.enriching[item.answer_id])
                        ? " …"
                        : "";
                var saved = item.message_count > 0 ? " ●" : "";
                var selected = item.answer_id === state.activeAnswerId ? " selected" : "";
                return (
                    '<option value="' +
                    item.answer_id +
                    '"' +
                    selected +
                    ">" +
                    "Q" +
                    qNum +
                    ": " +
                    escapeHtml(truncateStem(item.stem)) +
                    saved +
                    pending +
                    "</option>"
                );
            })
            .join("");
    }

    function attachmentChip(msg) {
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
            '<span class="chat-attach__meta"><span class="chat-attach__label">Attached image</span>' +
            '<span class="chat-attach__name">' +
            escapeHtml(label) +
            "</span></span></a>"
        );
    }

    function updateComposeUi() {
        var input = document.getElementById("ai-tutor-chat-input");
        var attach = document.getElementById("ai-tutor-image-label");
        var composer = document.getElementById("ai-tutor-chat");
        var isFaculty = state.screen === "faculty";
        var isSolution = state.screen === "solution";
        var canAttach = !isSolution;

        if (composer) composer.classList.toggle("hidden", isSolution);
        if (input) {
            input.placeholder = isFaculty
                ? "Ask your professor about this question…"
                : "Ask how to solve this step by step…";
        }
        if (attach) attach.classList.toggle("hidden", !canAttach);
        if (!canAttach) clearImageSelection();
    }

    function setTutorScreen(screen) {
        if (screen === "faculty") state.screen = "faculty";
        else if (screen === "solution") state.screen = "solution";
        else state.screen = "ai";

        var ai = document.getElementById("ai-tutor-screen-ai");
        var solution = document.getElementById("ai-tutor-screen-solution");
        var faculty = document.getElementById("ai-tutor-screen-faculty");
        if (ai) ai.classList.toggle("hidden", state.screen !== "ai");
        if (solution) solution.classList.toggle("hidden", state.screen !== "solution");
        if (faculty) faculty.classList.toggle("hidden", state.screen !== "faculty");
        document.querySelectorAll("[data-tutor-screen]").forEach(function (btn) {
            var active = btn.getAttribute("data-tutor-screen") === state.screen;
            btn.classList.toggle("ai-tutor-modal__tab--active", active);
            btn.setAttribute("aria-selected", active ? "true" : "false");
        });
        updateComposeUi();
    }

    function renderFacultyThread(item) {
        var container = document.getElementById("ai-tutor-faculty-thread");
        if (!container) return;
        var messages = (item && item.concern_messages) || [];
        if (!messages.length) {
            container.innerHTML =
                '<p class="chat-thread__empty">No messages yet. Start the conversation below.</p>';
            return;
        }
        container.innerHTML = messages
            .map(function (msg) {
                var isSelf = msg.author_role === "student";
                var side = isSelf ? "out" : "in";
                var initials = msg.author_initials || (isSelf ? "YOU" : "FA");
                var header = isSelf
                    ? "You"
                    : escapeHtml(msg.author_name || "Faculty") +
                      (item && item.topic ? " · " + escapeHtml(item.topic) : "");
                var bodyHtml = msg.body
                    ? '<p class="chat-bubble__text">' +
                      escapeHtml(msg.body).replace(/\n/g, "<br>") +
                      "</p>"
                    : "";
                return (
                    '<div class="chat-row chat-row--' +
                    side +
                    '">' +
                    (isSelf
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
                    attachmentChip(msg) +
                    "</div>" +
                    '<p class="chat-row__time">' +
                    escapeHtml(formatTimestamp(msg.created_at)) +
                    "</p></div>" +
                    (isSelf
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

    function renderFacultyNotes(item) {
        renderFacultyThread(item);
    }

    function activeItem() {
        return state.items.find(function (item) {
            return item.answer_id === state.activeAnswerId;
        });
    }

    function renderSolutionSteps(stepsEl, steps) {
        if (!stepsEl) return;
        stepsEl.innerHTML = (steps || [])
            .map(function (step, index) {
                var text = String(step || "").trim();
                var looksMath =
                    /[=+\-×÷^√]|\\frac|\d/.test(text) &&
                    text.length < 120 &&
                    !/[.!?]{2,}/.test(text) &&
                    text.split(" ").length <= 12;
                var bodyClass = looksMath
                    ? "ai-tutor-solution-timeline__math"
                    : "ai-tutor-solution-timeline__instruction";
                return (
                    '<li class="ai-tutor-solution-timeline__item">' +
                    '<span class="ai-tutor-solution-timeline__index" aria-hidden="true">' +
                    (index + 1) +
                    "</span>" +
                    '<div class="ai-tutor-solution-timeline__body examiq-math-block">' +
                    '<p class="' +
                    bodyClass +
                    '">' +
                    escapeHtml(text).replace(/\n/g, "<br>") +
                    "</p></div></li>"
                );
            })
            .join("");
    }

    function truncateFeedback(text, maxLen) {
        var raw = String(text || "").trim();
        if (!raw) return "";
        if (raw.length <= maxLen) return raw;
        var cut = raw.slice(0, maxLen);
        var last = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("! "), cut.lastIndexOf("? "));
        if (last > 40) return cut.slice(0, last + 1).trim();
        return cut.trim() + "…";
    }

    function studentIdentity() {
        var config = getConfig();
        var name = config.studentName || "You";
        var initials = (config.studentInitials || "").trim();
        if (!initials) {
            var parts = String(name).trim().split(/\s+/);
            initials =
                parts.length >= 2
                    ? (parts[0][0] + parts[1][0]).toUpperCase()
                    : String(name).slice(0, 2).toUpperCase();
        }
        return {
            name: name,
            initials: initials || "YOU",
            avatarUrl: config.studentAvatarUrl || "",
        };
    }

    function avatarHtml(side, identity) {
        if (side === "out" && identity.avatarUrl) {
            return (
                '<div class="chat-avatar chat-avatar--sm chat-avatar--photo" aria-hidden="true">' +
                '<img src="' +
                escapeHtml(identity.avatarUrl) +
                '" alt="">' +
                "</div>"
            );
        }
        var label = side === "out" ? identity.initials : "AI";
        var cls =
            side === "out"
                ? "chat-avatar chat-avatar--sm chat-avatar--self"
                : "chat-avatar chat-avatar--sm chat-avatar--ai";
        return (
            '<div class="' + cls + '" aria-hidden="true">' + escapeHtml(label) + "</div>"
        );
    }

    function renderFeedbackPanel() {
        var item = activeItem();
        var stemEl = document.getElementById("ai-tutor-stem");
        var metaEl = document.getElementById("ai-tutor-meta");
        var userAnswerEl = document.getElementById("ai-tutor-user-answer");
        var correctAnswerEl = document.getElementById("ai-tutor-correct-answer");
        var visualHost = document.getElementById("ai-tutor-solution-visual");
        if (!item || !stemEl) return;

        stemEl.textContent = item.stem;
        renderFacultyNotes(item);

        if (userAnswerEl) {
            userAnswerEl.textContent = item.user_answer || "No answer";
        }
        if (correctAnswerEl) {
            correctAnswerEl.textContent =
                item.correct_answer || item.final_answer || "Unknown";
        }

        if (visualHost && window.ExamiQUI && window.ExamiQUI.renderTutorVisualResponse) {
            var why = "";
            if (!item.is_correct) {
                why = truncateFeedback(item.feedback || "", 220);
            }
            var structured = null;
            for (var i = state.messages.length - 1; i >= 0; i -= 1) {
                var msg = state.messages[i];
                if (msg && msg.role === "assistant" && msg.structured) {
                    structured = msg.structured;
                    break;
                }
            }
            window.ExamiQUI.renderTutorVisualResponse(visualHost, {
                structured: structured,
                correctionSteps: item.correction_steps || [],
                finalAnswer: item.final_answer || item.correct_answer || "",
                why: why,
                progressive: false,
            });
        }

        if (metaEl) {
            metaEl.textContent =
                (item.topic || "") + (item.difficulty ? " · " + item.difficulty : "");
        }

        katexRender(document.getElementById("ai-tutor-feedback-panel"));
    }

    function renderMessages() {
        var container = document.getElementById("ai-tutor-messages");
        if (!container) return;
        var identity = studentIdentity();
        if (!state.messages.length) {
            container.innerHTML =
                '<p class="chat-thread__empty">Ask a short question about this problem.</p>';
            return;
        }
        container.innerHTML = "";
        state.messages.forEach(function (msg) {
            var isUser = msg.role === "user";
            var side = isUser ? "out" : "in";
            var header = isUser ? identity.name : "AI Tutor";
            var row = document.createElement("div");
            row.className = "chat-row chat-row--" + side;

            var body = document.createElement("div");
            body.className = "chat-row__body";
            body.innerHTML = '<p class="chat-row__header">' + escapeHtml(header) + "</p>";

            var bubble = document.createElement("div");
            bubble.className =
                "chat-bubble chat-bubble--" + side + " examiq-math-block";

            if (isUser) {
                var bodyHtml = msg.content
                    ? '<p class="chat-bubble__text">' +
                      escapeHtml(msg.content).replace(/\n/g, "<br>") +
                      "</p>"
                    : "";
                bubble.innerHTML = bodyHtml + attachmentChip(msg);
            } else if (window.ExamiQUI && window.ExamiQUI.renderTutorVisualResponse) {
                var host = document.createElement("div");
                host.className = "tutor-visual-host tutor-visual-host--chat";
                bubble.appendChild(host);
                window.ExamiQUI.renderTutorVisualResponse(host, {
                    structured: msg.structured || null,
                    raw: msg.content || "",
                    progressive: false,
                });
            } else {
                bubble.innerHTML =
                    '<p class="chat-bubble__text">' +
                    escapeHtml(msg.content || "").replace(/\n/g, "<br>") +
                    "</p>";
            }

            body.appendChild(bubble);
            if (isUser) {
                row.appendChild(body);
                row.insertAdjacentHTML("beforeend", avatarHtml("out", identity));
            } else {
                row.insertAdjacentHTML("afterbegin", avatarHtml("in", identity));
                row.appendChild(body);
            }
            container.appendChild(row);
        });
        katexRender(container);
        container.scrollTop = container.scrollHeight;
    }

    function pickDefaultAnswer() {
        if (state.activeAnswerId) return;
        var wrong = state.items.filter(function (item) {
            return !item.is_correct;
        });
        var pool = wrong.length ? wrong : state.items;
        if (pool.length) {
            state.activeAnswerId = pool[0].answer_id;
        }
    }

    function showContent() {
        var loading = document.getElementById("ai-tutor-loading");
        var content = document.getElementById("ai-tutor-content");
        var errorEl = document.getElementById("ai-tutor-error");
        if (loading) loading.classList.add("hidden");
        if (errorEl) errorEl.classList.add("hidden");
        if (content) content.classList.remove("hidden");
        pickDefaultAnswer();
        setTutorScreen(state.preferredScreen || "solution");
        renderQuestionSelect();
        renderFeedbackPanel();
        renderMessages();
    }

    function clearImageSelection() {
        var input = document.getElementById("ai-tutor-chat-image");
        var nameEl = document.getElementById("ai-tutor-image-name");
        if (input) input.value = "";
        if (nameEl) {
            nameEl.textContent = "";
            nameEl.classList.add("hidden");
        }
    }

    function validateImageFile(file) {
        if (!file) return null;
        if (file.size > MAX_IMAGE_BYTES) {
            return "Image must be 5 MB or smaller.";
        }
        var type = (file.type || "").toLowerCase();
        var name = (file.name || "").toLowerCase();
        var okType = ALLOWED_IMAGE_TYPES[type];
        var okExt = /\.(jpe?g|png|webp)$/.test(name);
        if (!okType && !okExt) {
            return "Use a JPEG, PNG, or WebP image.";
        }
        return null;
    }

    async function sendFacultyMessage(message, imageFile) {
        if (state.sending) return;
        var item = activeItem();
        if (!item) return;
        var url = concernUrlForAnswer(item.answer_id);
        if (!url) {
            if (typeof showToast === "function") {
                showToast("Could not find concern endpoint for this question.", "error");
            }
            return;
        }
        if (!message.trim() && !imageFile) {
            if (typeof showToast === "function") {
                showToast("Add a message or photo.", "warning");
            }
            return;
        }
        var imageError = validateImageFile(imageFile);
        if (imageError) {
            if (typeof showToast === "function") showToast(imageError, "error");
            return;
        }

        state.sending = true;
        var btn = document.getElementById("ai-tutor-send-btn");
        if (btn && window.ExamiQUI && window.ExamiQUI.setButtonLoading) {
            window.ExamiQUI.setButtonLoading(btn, true, "Sending…");
        }
        try {
            var fd = new FormData();
            fd.append("csrfmiddlewaretoken", getConfig().csrfToken || "");
            fd.append("body", message.trim());
            if (imageFile) fd.append("image", imageFile);
            var resp = await fetch(url, {
                method: "POST",
                body: fd,
                headers: {
                    Accept: "application/json",
                    "X-CSRFToken": getConfig().csrfToken || "",
                    "X-Requested-With": "XMLHttpRequest",
                },
                credentials: "same-origin",
            });
            var data = await resp.json().catch(function () {
                return {};
            });
            if (!resp.ok) throw new Error(data.error || "Could not send message.");
            item.concern_messages = data.messages || [];
            renderFacultyThread(item);
            clearImageSelection();
            if (typeof showToast === "function") showToast("Message sent to faculty.", "success");
        } catch (err) {
            if (typeof showToast === "function") {
                showToast(err.message || "Could not send message.", "error");
            }
        } finally {
            state.sending = false;
            if (btn && window.ExamiQUI && window.ExamiQUI.setButtonLoading) {
                window.ExamiQUI.setButtonLoading(btn, false);
            }
        }
    }

    async function sendMessage(message, imageFile) {
        if (state.sending) return;
        var config = getConfig();
        if (!config.chatUrl) return;
        if (!message.trim() && !imageFile) return;

        var imageError = validateImageFile(imageFile);
        if (imageError) {
            if (typeof showToast === "function") showToast(imageError, "error");
            return;
        }

        state.sending = true;
        var previewUrl = imageFile ? URL.createObjectURL(imageFile) : "";
        state.messages.push({
            role: "user",
            content: message.trim(),
            image_url: previewUrl,
            image_name: imageFile ? imageFile.name : "",
        });
        renderMessages();
        clearImageSelection();

        try {
            var resp;
            if (imageFile) {
                var fd = new FormData();
                fd.append("message", message.trim());
                fd.append("answer_id", String(state.activeAnswerId || ""));
                fd.append("image", imageFile);
                resp = await fetch(config.chatUrl, {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": config.csrfToken,
                        Accept: "application/json",
                    },
                    credentials: "same-origin",
                    body: fd,
                });
            } else {
                resp = await fetch(config.chatUrl, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": config.csrfToken,
                        Accept: "application/json",
                    },
                    credentials: "same-origin",
                    body: JSON.stringify({
                        message: message.trim(),
                        answer_id: state.activeAnswerId,
                    }),
                });
            }
            var data = await resp.json();
            if (!resp.ok) {
                throw new Error(data.error || "Send failed");
            }
            if (data.user_message) {
                state.messages[state.messages.length - 1] = data.user_message;
            }
            state.messages.push({ role: "assistant", content: data.reply, structured: data.structured || null });
            if (data.active_answer_id) {
                state.activeAnswerId = data.active_answer_id;
            }
            var item = activeItem();
            if (item) {
                item.message_count = (item.message_count || 0) + 2;
            }
            renderQuestionSelect();
            renderMessages();
            renderFeedbackPanel();
        } catch (err) {
            state.messages.pop();
            renderMessages();
            if (typeof showToast === "function") {
                showToast(err.message || "Could not send message.", "error");
            }
        } finally {
            if (previewUrl) URL.revokeObjectURL(previewUrl);
            state.sending = false;
        }
    }

    async function openTutorModal(options) {
        options = options || {};
        var cfg = getConfig();
        var sessionId = options.sessionId || cfg.defaultSessionId || null;
        if (sessionId) {
            applySessionUrls(sessionId);
        }
        if (options.answerId) {
            state.activeAnswerId = options.answerId;
        }
        state.reviewMode = !!options.reviewMode;
        state.includeAll = !!options.includeAll || !!options.reviewMode;
        state.preferredScreen =
            options.screen === "faculty"
                ? "faculty"
                : options.screen === "ai"
                  ? "ai"
                  : "solution";

        if (options.answerId) {
            markAnswerNotificationsRead(options.answerId);
        }

        openModal();
        var loading = document.getElementById("ai-tutor-loading");
        var content = document.getElementById("ai-tutor-content");
        var errorEl = document.getElementById("ai-tutor-error");
        if (loading) loading.classList.remove("hidden");
        if (content) content.classList.add("hidden");
        if (errorEl) errorEl.classList.add("hidden");

        try {
            if (!getConfig().historyUrl) {
                throw new Error("no session");
            }
            await loadHistoryForAnswer(state.activeAnswerId || null);
            if (state.activeAnswerId) {
                await loadHistoryForAnswer(state.activeAnswerId);
            }
            showContent();
            state.loaded = true;
            if (!state.reviewMode) {
                enrichPendingFeedback();
            }
        } catch (err) {
            showError(
                getConfig().historyUrl
                    ? "Could not load tutor feedback. Try again from your session summary."
                    : "Complete a review session first, then open AI Tutor to discuss your answers."
            );
        }
    }

    window.ExamiQTutor = window.ExamiQTutor || {};
    window.ExamiQTutor.open = openTutorModal;

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-dismiss-ai-tutor]").forEach(function (el) {
            el.addEventListener("click", closeModal);
        });

        document.querySelectorAll("[data-open-ai-tutor]").forEach(function (el) {
            el.addEventListener("click", function (event) {
                event.preventDefault();
                openTutorModal({ includeAll: true, screen: "ai" });
            });
        });

        var openBtn = document.getElementById("open-ai-tutor-btn");
        if (openBtn) {
            openBtn.addEventListener("click", function (event) {
                event.preventDefault();
                openTutorModal({ includeAll: true });
            });
        }

        document.querySelectorAll(".open-tutor-btn").forEach(function (btn) {
            btn.addEventListener("click", function (event) {
                event.preventDefault();
                var sessionId = parseInt(btn.getAttribute("data-session-id"), 10);
                var answerId = parseInt(btn.getAttribute("data-answer-id"), 10);
                var screen = btn.getAttribute("data-tutor-screen") || "faculty";
                openTutorModal({
                    sessionId: sessionId,
                    answerId: answerId,
                    screen: screen,
                });
            });
        });

        var select = document.getElementById("ai-tutor-question-select");
        if (select) {
            select.addEventListener("change", function () {
                var answerId = parseInt(select.value, 10);
                if (!isNaN(answerId)) {
                    selectAnswer(answerId);
                }
            });
        }

        document.querySelectorAll("[data-tutor-screen]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                setTutorScreen(btn.getAttribute("data-tutor-screen"));
            });
        });

        var imageInput = document.getElementById("ai-tutor-chat-image");
        var imageName = document.getElementById("ai-tutor-image-name");
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
                    imageName.textContent = file.name + " (" + Math.round(file.size / 1024) + " KB)";
                    imageName.classList.remove("hidden");
                }
            });
        }

        var form = document.getElementById("ai-tutor-chat-form");
        var input = document.getElementById("ai-tutor-chat-input");
        if (form && input) {
            form.addEventListener("submit", function (event) {
                event.preventDefault();
                var text = input.value;
                var file = imageInput && imageInput.files ? imageInput.files[0] : null;
                if (state.screen === "faculty") {
                    input.value = "";
                    sendFacultyMessage(text, file);
                } else {
                    input.value = "";
                    sendMessage(text, file);
                }
            });
            input.addEventListener("keydown", function (event) {
                if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
                }
            });
        }

        var config = getConfig();
        var params = new URLSearchParams(window.location.search);
        var openAnswer = params.get("answer_id");
        var openTutor = params.get("open_tutor") === "1";
        if (config.openOnLoad || openTutor) {
            var answerId = config.openAnswerId || (openAnswer ? parseInt(openAnswer, 10) : null);
            var openBtn = answerId
                ? document.querySelector(
                      '.open-tutor-btn[data-answer-id="' + answerId + '"]'
                  )
                : null;
            var sessionId = openBtn
                ? parseInt(openBtn.getAttribute("data-session-id"), 10)
                : config.defaultSessionId || null;
            openTutorModal({
                sessionId: sessionId || undefined,
                answerId: answerId || null,
                includeAll: true,
                screen: openTutor ? "ai" : config.openScreen || "ai",
            });
        }
    });
})();
