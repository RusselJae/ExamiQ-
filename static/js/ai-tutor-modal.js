(function () {
    "use strict";

    var state = {
        items: [],
        messages: [],
        activeAnswerId: null,
        sending: false,
        loaded: false,
        enriching: {},
        screen: "ai",
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

    function feedbackUrlForAnswer(answerId) {
        var config = getConfig();
        if (!config.feedbackUrl) return "";
        var sep = config.feedbackUrl.indexOf("?") >= 0 ? "&" : "?";
        return config.feedbackUrl + sep + "answer_id=" + encodeURIComponent(answerId);
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
        // Active first, then remaining — one at a time to avoid host timeouts.
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
            enrichAnswerFeedback(answerId);
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
            .map(function (item, index) {
                var pending = item.needs_ai || state.enriching[item.answer_id] ? " …" : "";
                var saved = item.message_count > 0 ? " ●" : "";
                var selected = item.answer_id === state.activeAnswerId ? " selected" : "";
                return (
                    '<option value="' +
                    item.answer_id +
                    '"' +
                    selected +
                    ">" +
                    "Q" +
                    (index + 1) +
                    ": " +
                    escapeHtml(truncateStem(item.stem)) +
                    saved +
                    pending +
                    "</option>"
                );
            })
            .join("");
    }

    function setTutorScreen(screen) {
        state.screen = screen === "faculty" ? "faculty" : "ai";
        var ai = document.getElementById("ai-tutor-screen-ai");
        var faculty = document.getElementById("ai-tutor-screen-faculty");
        if (ai) ai.classList.toggle("hidden", state.screen !== "ai");
        if (faculty) faculty.classList.toggle("hidden", state.screen !== "faculty");
        document.querySelectorAll("[data-tutor-screen]").forEach(function (btn) {
            var active = btn.getAttribute("data-tutor-screen") === state.screen;
            btn.classList.toggle("ai-tutor-modal__tab--active", active);
            btn.setAttribute("aria-selected", active ? "true" : "false");
        });
    }

    function renderFacultyNotes(item) {
        var el = document.getElementById("ai-tutor-faculty-notes");
        if (!el) return;
        var notes = (item && item.faculty_notes) || [];
        if (!notes.length) {
            el.textContent = "No faculty note for this question yet.";
            return;
        }
        el.innerHTML = notes
            .map(function (note) {
                return '<p class="mb-3">' + escapeHtml(note).replace(/\n/g, "<br>") + "</p>";
            })
            .join("");
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
                return (
                    '<li class="ai-tutor-solution-timeline__item">' +
                    '<span class="ai-tutor-solution-timeline__index" aria-hidden="true">' +
                    (index + 1) +
                    "</span>" +
                    '<div class="ai-tutor-solution-timeline__body examiq-math-block">' +
                    escapeHtml(step).replace(/\n/g, "<br>") +
                    "</div></li>"
                );
            })
            .join("");
    }

    function renderFeedbackPanel() {
        var item = activeItem();
        var stemEl = document.getElementById("ai-tutor-stem");
        var whyEl = document.getElementById("ai-tutor-why");
        var stepsEl = document.getElementById("ai-tutor-steps");
        var metaEl = document.getElementById("ai-tutor-meta");
        var finalEl = document.getElementById("ai-tutor-final");
        var finalSection = document.getElementById("ai-tutor-final-section");
        var whySection = document.getElementById("ai-tutor-why-section");
        var stepsSection = document.getElementById("ai-tutor-steps-section");
        if (!item || !stemEl) return;

        stemEl.textContent = item.stem;
        renderFacultyNotes(item);

        if (state.enriching[item.answer_id]) {
            if (whySection) whySection.classList.remove("hidden");
            if (whyEl) {
                whyEl.innerHTML = escapeHtml(item.feedback || "Loading AI feedback…").replace(/\n/g, "<br>");
                whyEl.insertAdjacentHTML(
                    "beforeend",
                    '<p class="text-sm text-examiq-slate mt-2">Enriching with AI tutor feedback…</p>'
                );
            }
            if (stepsSection) {
                if (item.correction_steps && item.correction_steps.length) {
                    stepsSection.classList.remove("hidden");
                    renderSolutionSteps(stepsEl, item.correction_steps);
                } else {
                    stepsSection.classList.add("hidden");
                }
            }
        } else if (item.is_correct) {
            if (whySection) whySection.classList.add("hidden");
            if (stepsSection) stepsSection.classList.remove("hidden");
            if (item.correction_steps && item.correction_steps.length) {
                renderSolutionSteps(stepsEl, item.correction_steps);
            } else if (stepsEl) {
                renderSolutionSteps(stepsEl, [item.feedback || "You solved this correctly."]);
            }
        } else {
            if (whySection) whySection.classList.remove("hidden");
            if (whyEl) {
                whyEl.innerHTML = escapeHtml(item.feedback || "").replace(/\n/g, "<br>");
            }
            if (stepsSection) {
                if (item.correction_steps && item.correction_steps.length) {
                    stepsSection.classList.remove("hidden");
                    renderSolutionSteps(stepsEl, item.correction_steps);
                } else {
                    stepsSection.classList.add("hidden");
                }
            }
        }

        if (finalSection && finalEl) {
            if (item.final_answer && item.final_answer !== "Unknown") {
                finalSection.classList.remove("hidden");
                finalEl.textContent = item.final_answer;
            } else {
                finalSection.classList.add("hidden");
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
                return (
                    '<div class="ai-tutor-chat__bubble ' +
                    cls +
                    ' examiq-math-block">' +
                    escapeHtml(msg.content).replace(/\n/g, "<br>") +
                    "</div>"
                );
            })
            .join("");
        container.scrollTop = container.scrollHeight;
        katexRender(container);
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
        setTutorScreen("ai");
        renderQuestionSelect();
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
            renderQuestionSelect();
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
            if (state.activeAnswerId) {
                await loadHistoryForAnswer(state.activeAnswerId);
            }
            showContent();
            state.loaded = true;
            // Enrich in background after UI is usable — do not block open.
            enrichPendingFeedback();
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
