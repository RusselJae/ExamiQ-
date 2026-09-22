/**
 * Answer review grid: result borders + optional pace bars (quick/steady/slow).
 * Unanswered cells keep a missed border and show no pace dashes.
 */
(function () {
    "use strict";

    function resolveEl(value) {
        if (!value) return null;
        return typeof value === "string" ? document.getElementById(value) : value;
    }

    function paceLabel(pace) {
        if (pace === "quick") return "Quick";
        if (pace === "steady") return "Steady";
        if (pace === "slow") return "Slow";
        if (pace === "unanswered") return "Unanswered";
        return "—";
    }

    function renderPaceBars(count) {
        var html = '<span class="answer-review__pace-bars" aria-hidden="true">';
        for (var i = 0; i < 3; i++) {
            html += i < count ? '<i class="is-on"></i>' : "<i></i>";
        }
        return html + "</span>";
    }

    function cellTitle(point, index, showPace) {
        var n = point.label || index;
        if (point.unanswered) {
            return "Q" + n + ": Unanswered";
        }
        var result = point.is_correct ? "Correct" : "Missed";
        if (!showPace) {
            return "Q" + n + ": " + result;
        }
        return "Q" + n + ": " + result + " · " + paceLabel(point.pace);
    }

    /**
     * @param {object} options
     * @param {string|HTMLElement} options.grid
     * @param {string|HTMLElement} [options.wrapEl]
     * @param {string|HTMLElement} [options.emptyEl]
     * @param {string|HTMLElement} [options.legend]
     * @param {NodeList|Array|string} [options.toggleButtons] — buttons with data-review-mode
     * @param {object} options.data — question_trends payload (uses .review)
     * @param {boolean} [options.clickable]
     * @param {string} [options.answerUrlTemplate]
     * @param {string} [options.defaultMode] — "pace" | "result"
     */
    function renderSessionAnswerReview(options) {
        options = options || {};
        var grid = resolveEl(options.grid);
        var wrapEl = resolveEl(options.wrapEl);
        var emptyEl = resolveEl(options.emptyEl);
        var legend = resolveEl(options.legend);
        var data = options.data || {};
        var points = data.review || [];
        var mode = options.defaultMode === "result" ? "result" : "pace";

        if (!grid) return null;

        var toggleButtons = options.toggleButtons;
        if (typeof toggleButtons === "string") {
            toggleButtons = document.querySelectorAll(toggleButtons);
        }

        function showPace() {
            return mode === "pace";
        }

        function syncToggle() {
            if (!toggleButtons) return;
            Array.prototype.forEach.call(toggleButtons, function (btn) {
                var active = btn.getAttribute("data-review-mode") === mode;
                btn.classList.toggle("is-active", active);
                btn.setAttribute("aria-pressed", active ? "true" : "false");
            });
            if (legend) {
                legend.classList.toggle("answer-review__legend--result-only", !showPace());
            }
        }

        function build() {
            syncToggle();

            if (!points.length) {
                grid.innerHTML = "";
                if (emptyEl) emptyEl.classList.remove("hidden");
                if (wrapEl) wrapEl.classList.add("hidden");
                return;
            }
            if (emptyEl) emptyEl.classList.add("hidden");
            if (wrapEl) wrapEl.classList.remove("hidden");

            var n = points.length;
            var size = Math.max(40, Math.min(56, Math.round(480 / Math.sqrt(n))));
            grid.style.setProperty("--answer-review-cell-size", size + "px");
            grid.setAttribute("data-mode", mode);

            grid.innerHTML = points
                .map(function (point, index) {
                    var unanswered = !!point.unanswered;
                    var correct = !!point.is_correct && !unanswered;
                    var borderCls = correct
                        ? "answer-review__cell--correct"
                        : "answer-review__cell--missed";
                    if (unanswered) {
                        borderCls += " answer-review__cell--unanswered";
                    }
                    var title = cellTitle(point, index + 1, showPace());
                    var barsHtml = "";
                    if (showPace() && !unanswered) {
                        barsHtml = renderPaceBars(Number(point.pace_bars) || 0);
                    }
                    return (
                        '<button type="button" class="answer-review__cell ' +
                        borderCls +
                        '" data-answer-id="' +
                        (point.answer_id || "") +
                        '" title="' +
                        title +
                        '" aria-label="' +
                        title +
                        '" role="listitem">' +
                        '<span class="answer-review__cell-num">' +
                        (point.label || index + 1) +
                        "</span>" +
                        barsHtml +
                        "</button>"
                    );
                })
                .join("");
        }

        grid.addEventListener("click", function (event) {
            if (options.clickable === false) return;
            var btn = event.target.closest(".answer-review__cell");
            if (!btn) return;
            var answerId = parseInt(btn.getAttribute("data-answer-id"), 10);
            if (!answerId) return;

            var template = options.answerUrlTemplate || "";
            if (template) {
                window.location.href = template
                    .replace("{id}", String(answerId))
                    .replace("{pk}", String(answerId))
                    .replace("/0/", "/" + answerId + "/");
                return;
            }

            if (!window.ExamiQTutor || !window.ExamiQTutor.open) return;
            window.ExamiQTutor.open({
                answerId: answerId,
                reviewMode: true,
                includeAll: true,
                screen: "solution",
            });
        });

        if (toggleButtons) {
            Array.prototype.forEach.call(toggleButtons, function (btn) {
                btn.addEventListener("click", function () {
                    var next = btn.getAttribute("data-review-mode");
                    if (next !== "pace" && next !== "result") return;
                    mode = next;
                    build();
                });
            });
        }

        build();
        return { rebuild: build };
    }

    window.ExamiQUI = window.ExamiQUI || {};
    window.ExamiQUI.renderSessionAnswerReview = renderSessionAnswerReview;
})();
