(function () {
    "use strict";

    var state = {
        items: [],
        messages: [],
        activeAnswerId: null,
        sending: false,
        loaded: false,
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

    function historyUrlForAnswer(answerId) {
        var config = getConfig();
        if (!config.historyUrl) return "";
        if (!answerId) return config.historyUrl;
        var sep = config.historyUrl.indexOf("?") >= 0 ? "&" : "?";
        return config.historyUrl + sep + "answer_id=" + encodeURIComponent(answerId);
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

    function renderPills() {
        var container = document.getElementById("ai-tutor-question-pills");
        var countEl = document.getElementById("ai-tutor-review-count");
        if (!container) return;

        var reviewItems = state.items.filter(function (item) {
            return !item.is_correct;
        });
        if (!reviewItems.length) {
            reviewItems = state.items;
        }

        if (countEl) {
            countEl.textContent = "Reviewing " + reviewItems.length + " item" + (reviewItems.length === 1 ? "" : "s");
        }

        container.innerHTML = reviewItems
            .map(function (item, index) {
                var active = item.answer_id === state.activeAnswerId ? " ai-tutor-pill--active" : "";
                var saved = item.message_count > 0 ? ' <span class="ai-tutor-pill__saved" title="Saved conversation">●</span>' : "";
                return (
                    '<button type="button" class="ai-tutor-pill' + active + '" data-answer-id="' +
                    item.answer_id + '" role="tab" aria-selected="' + (active ? "true" : "false") + '">' +
                    "Q" + (index + 1) + ": " + escapeHtml(truncateStem(item.stem)) + saved +
                    "</button>"
                );
            })
            .join("");

        container.querySelectorAll(".ai-tutor-pill").forEach(function (pill) {
            pill.addEventListener("click", async function () {
                var answerId = parseInt(pill.dataset.answerId, 10);
                state.activeAnswerId = answerId;
                try {
                    await loadHistoryForAnswer(answerId);
                    renderPills();
                    renderFeedbackPanel();
                    renderMessages();
                } catch (err) {
                    if (typeof showToast === "function") {
                        showToast("Could not load saved conversation for this question.", "error");
                    }
                }
            });
        });
    }

    function activeItem() {
        return state.items.find(function (item) {
            return item.answer_id === state.activeAnswerId;
        });
    }

    function renderFeedbackPanel() {
        var item = activeItem();
        var stemEl = document.getElementById("ai-tutor-stem");
        var whyEl = document.getElementById("ai-tutor-why");
        var stepsEl = document.getElementById("ai-tutor-steps");
        var metaEl = document.getElementById("ai-tutor-meta");
        var whySection = document.getElementById("ai-tutor-why-section");
        var stepsSection = document.getElementById("ai-tutor-steps-section");
        if (!item || !stemEl) return;

        stemEl.textContent = "Review: " + item.stem;

        if (item.is_correct) {
            if (whySection) whySection.classList.add("hidden");
            if (stepsSection) stepsSection.classList.remove("hidden");
            if (stepsEl) {
                stepsEl.innerHTML = "<li>" + escapeHtml(item.feedback).replace(/\n/g, "</li><li>") + "</li>";
            }
        } else {
            if (whySection) whySection.classList.remove("hidden");
            if (whyEl) {
                whyEl.innerHTML = escapeHtml(item.feedback).replace(/\n/g, "<br>");
            }
            if (stepsSection) {
                if (item.correction_steps && item.correction_steps.length) {
                    stepsSection.classList.remove("hidden");
                    stepsEl.innerHTML = item.correction_steps
                        .map(function (step) {
                            return "<li>" + escapeHtml(step) + "</li>";
                        })
                        .join("");
                } else {
                    stepsSection.classList.add("hidden");
                }
            }
        }

        if (metaEl) {
            metaEl.textContent =
                "Recommended concepts: " + item.topic + " · Difficulty: " + (item.difficulty || "—");
        }

        katexRender(document.getElementById("ai-tutor-feedback-panel"));
    }

    function renderMessages() {
        var container = document.getElementById("ai-tutor-messages");
        if (!container) return;
        container.innerHTML = state.messages
            .map(function (msg) {
                var cls = msg.role === "user" ? "ai-tutor-chat__bubble--user" : "ai-tutor-chat__bubble--assistant";
                return '<div class="ai-tutor-chat__bubble ' + cls + '">' + escapeHtml(msg.content) + "</div>";
            })
            .join("");
        container.scrollTop = container.scrollHeight;
    }

    async function loadFeedback() {
        var config = getConfig();
        if (!config.feedbackUrl) return;
        var resp = await fetch(config.feedbackUrl, {
            method: "POST",
            headers: {
                "X-CSRFToken": config.csrfToken,
                Accept: "application/json",
            },
            credentials: "same-origin",
        });
        if (!resp.ok) throw new Error("feedback failed");
        var data = await resp.json();
        if (data.items && data.items.length) {
            data.items.forEach(function (fbItem) {
                var existing = state.items.find(function (item) {
                    return item.answer_id === fbItem.answer_id;
                });
                if (existing) {
                    existing.feedback = fbItem.feedback;
                } else {
                    state.items.push(fbItem);
                }
            });
        }
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
        renderPills();
        renderFeedbackPanel();
        renderMessages();
    }

    async function sendMessage(message) {
        if (state.sending) return;
        var config = getConfig();
        if (!config.chatUrl || !message.trim()) return;

        state.sending = true;
        state.messages.push({ role: "user", content: message.trim() });
        renderMessages();

        try {
            var resp = await fetch(config.chatUrl, {
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
            var data = await resp.json();
            if (!resp.ok) {
                throw new Error(data.error || "Send failed");
            }
            state.messages.push({ role: "assistant", content: data.reply });
            if (data.active_answer_id) {
                state.activeAnswerId = data.active_answer_id;
            }
            var item = activeItem();
            if (item) {
                item.message_count = (item.message_count || 0) + 2;
            }
            renderPills();
            renderMessages();
        } catch (err) {
            state.messages.pop();
            renderMessages();
            if (typeof showToast === "function") {
                showToast(err.message || "Could not send message.", "error");
            }
        } finally {
            state.sending = false;
        }
    }

    async function openTutorModal() {
        openModal();
        var loading = document.getElementById("ai-tutor-loading");
        var content = document.getElementById("ai-tutor-content");
        var errorEl = document.getElementById("ai-tutor-error");
        if (loading) loading.classList.remove("hidden");
        if (content) content.classList.add("hidden");
        if (errorEl) errorEl.classList.add("hidden");

        try {
            await loadHistoryForAnswer(null);
            await loadFeedback();
            if (state.activeAnswerId) {
                await loadHistoryForAnswer(state.activeAnswerId);
            }
            showContent();
            state.loaded = true;
        } catch (err) {
            showError("Could not load tutor feedback. Try again from your session summary.");
        }
    }

    window.ExamiQTutor = window.ExamiQTutor || {};
    window.ExamiQTutor.open = openTutorModal;

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-dismiss-ai-tutor]").forEach(function (el) {
            el.addEventListener("click", closeModal);
        });

        var openBtn = document.getElementById("open-ai-tutor-btn");
        if (openBtn) {
            openBtn.addEventListener("click", function (event) {
                event.preventDefault();
                openTutorModal();
            });
        }

        var form = document.getElementById("ai-tutor-chat-form");
        var input = document.getElementById("ai-tutor-chat-input");
        if (form && input) {
            form.addEventListener("submit", function (event) {
                event.preventDefault();
                var text = input.value;
                input.value = "";
                sendMessage(text);
            });
        }

        var config = getConfig();
        if (config.openOnLoad) {
            openTutorModal();
        }
    });
})();
