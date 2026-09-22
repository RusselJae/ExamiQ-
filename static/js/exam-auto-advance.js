(function () {
    "use strict";

    var advanceTimer = null;

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

    function clearAdvanceTimer() {
        if (advanceTimer) {
            clearTimeout(advanceTimer);
            advanceTimer = null;
        }
    }

    function scheduleAdvance(revealCard) {
        clearAdvanceTimer();
        var ms = parseInt(revealCard.dataset.revealMs, 10) || 1500;
        var url = revealCard.dataset.resultsUrl || revealCard.dataset.advanceUrl;
        if (!url) return;

        advanceTimer = setTimeout(function () {
            if (typeof htmx !== "undefined") {
                htmx.ajax("GET", url, {
                    target: "#question-container",
                    swap: "innerHTML",
                });
            } else {
                window.location.href = url;
            }
        }, ms);
    }

    function initExamResultsReview(target) {
        var resultsCard = target.querySelector("[data-exam-results]");
        if (!resultsCard) return;
        var el = document.getElementById("exam-answer-review-data");
        if (!el || !window.ExamiQUI || !window.ExamiQUI.renderSessionAnswerReview) return;
        window.ExamiQUI.renderSessionAnswerReview({
            grid: "exam-answer-review-grid",
            wrapEl: "exam-answer-review-wrap",
            emptyEl: "exam-answer-review-empty",
            legend: "exam-answer-review-legend",
            toggleButtons: "#exam-results-card [data-review-mode]",
            data: JSON.parse(el.textContent),
            defaultMode: "pace",
            clickable: false,
        });
    }

    function handleRevealSwap(target) {
        var revealCard = target.querySelector("[data-exam-reveal]");
        if (revealCard) {
            katexRender(target);
            scheduleAdvance(revealCard);
            return;
        }
        initExamResultsReview(target);
    }

    document.body.addEventListener("htmx:beforeSwap", function (event) {
        if (event.detail.target && event.detail.target.id === "question-container") {
            clearAdvanceTimer();
        }
    });

    document.body.addEventListener("htmx:afterSwap", function (event) {
        if (event.detail.target && event.detail.target.id === "question-container") {
            handleRevealSwap(event.detail.target);
        }
    });

    document.addEventListener("DOMContentLoaded", function () {
        var container = document.getElementById("question-container");
        if (container) {
            handleRevealSwap(container);
        }
    });
})();
