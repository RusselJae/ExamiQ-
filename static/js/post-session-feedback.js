(function () {
    "use strict";

    function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text || "";
        return div.innerHTML;
    }

    function tierClass(tier) {
        if (tier === "high") return "confidence-tier-badge--high";
        if (tier === "average") return "confidence-tier-badge--average";
        if (tier === "low") return "confidence-tier-badge--low";
        return "confidence-tier-badge--none";
    }

    function tierLabel(tier) {
        const labels = {
            none: "No Confidence",
            low: "Low Confidence",
            average: "Average Confidence",
            high: "High Confidence",
        };
        return labels[tier] || tier;
    }

    function feedbackText(raw) {
        if (window.ExamiQUI && window.ExamiQUI.extractFeedbackText) {
            return window.ExamiQUI.extractFeedbackText(raw);
        }
        return String(raw || "").trim();
    }

    function renderItem(item, index) {
        const status = item.is_correct
            ? '<span class="feedback-status feedback-status--correct">Correct</span>'
            : item.timed_out
            ? '<span class="feedback-status feedback-status--timeout">Timed out</span>'
            : '<span class="feedback-status feedback-status--incorrect">Incorrect</span>';
        return (
            '<article class="feedback-card" id="feedback-item-' + item.answer_id + '">' +
            '<div class="feedback-card__header">' +
            '<span class="feedback-card__index">Q' + (index + 1) + "</span>" +
            status +
            '<span class="confidence-tier-badge ' + tierClass(item.confidence_tier) + '">' +
            escapeHtml(tierLabel(item.confidence_tier)) +
            "</span></div>" +
            '<p class="feedback-card__stem">' + escapeHtml(item.stem) + "</p>" +
            '<div class="feedback-card__body">' +
            '<p class="text-xs font-semibold uppercase tracking-wider text-examiq-slate mb-2">Feedback</p>' +
            '<div class="feedback-step-list">' + escapeHtml(feedbackText(item.feedback)).replace(/\n/g, "<br>") + "</div>" +
            "</div></article>"
        );
    }

    function openModal() {
        const modal = document.getElementById("post-session-feedback-modal");
        if (!modal) return;
        modal.classList.remove("hidden");
        document.body.classList.add("feedback-modal-open");
    }

    function closeModal() {
        const modal = document.getElementById("post-session-feedback-modal");
        if (!modal) return;
        modal.classList.add("hidden");
        document.body.classList.remove("feedback-modal-open");
    }

    function showError(message) {
        const loading = document.getElementById("post-session-feedback-loading");
        const errorEl = document.getElementById("post-session-feedback-error");
        const list = document.getElementById("post-session-feedback-list");
        if (loading) loading.classList.add("hidden");
        if (list) list.classList.add("hidden");
        if (errorEl) {
            errorEl.textContent = message;
            errorEl.classList.remove("hidden");
        }
    }

    function resetLoadingState() {
        const loading = document.getElementById("post-session-feedback-loading");
        const errorEl = document.getElementById("post-session-feedback-error");
        const list = document.getElementById("post-session-feedback-list");
        if (loading) loading.classList.remove("hidden");
        if (errorEl) {
            errorEl.textContent = "";
            errorEl.classList.add("hidden");
        }
        if (list) {
            list.classList.add("hidden");
            list.innerHTML = "";
        }
    }

    async function loadFeedback() {
        const config = window.ExamiQPostSessionFeedback;
        if (!config || !config.url) return;

        openModal();
        resetLoadingState();

        const loading = document.getElementById("post-session-feedback-loading");
        const list = document.getElementById("post-session-feedback-list");
        if (!loading || !list) return;

        try {
            const resp = await fetch(config.url, {
                method: "POST",
                headers: {
                    "X-CSRFToken": config.csrfToken,
                    Accept: "application/json",
                },
                credentials: "same-origin",
            });

            if (!resp.ok) {
                if (resp.status === 403) {
                    showError("Could not verify your session. Refresh the page and try again.");
                    return;
                }
                if (resp.status === 504 || resp.status === 502) {
                    showError("Feedback took too long to generate. Try again from your mistake log.");
                    return;
                }
                showError("Could not load feedback. Try again from your mistake log.");
                return;
            }

            const data = await resp.json();
            if (!data.items || !data.items.length) {
                showError("No feedback is available for this session yet.");
                return;
            }

            list.innerHTML = data.items.map(renderItem).join("");
            loading.classList.add("hidden");
            list.classList.remove("hidden");
        } catch (err) {
            showError("Could not load feedback. Check your connection and try again from your mistake log.");
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-dismiss-feedback-modal]").forEach(function (el) {
            el.addEventListener("click", closeModal);
        });
        if (window.ExamiQPostSessionFeedback && window.ExamiQPostSessionFeedback.url) {
            loadFeedback();
        }
    });
})();
