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

    function queryEl(value) {
        if (!value) return null;
        if (typeof value !== "string") return value;
        return document.querySelector(value);
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

    function shortConfidence(point) {
        if (point.confidence_label === "Guessing") return "Guess.";
        if (point.confidence_label === "Sure") return "Sure";
        return "";
    }

    function resultLabel(point) {
        if (point.unanswered) return "Unanswered";
        return point.is_correct ? "Correct" : "Missed";
    }

    function cellTitle(point, index, showPace) {
        var n = point.label || index;
        var parts = ["Q" + n + ": " + resultLabel(point)];
        var confidence = shortConfidence(point);
        if (confidence) parts.push(confidence);
        if (showPace && !point.unanswered) {
            parts.push(paceLabel(point.pace) + " pace");
        }
        return parts.join(" \u00b7 ");
    }

    /**
     * @param {object} options
     * @param {string|HTMLElement} options.grid
     * @param {string|HTMLElement} [options.wrapEl]
     * @param {string|HTMLElement} [options.emptyEl]
     * @param {string|HTMLElement} [options.legend]
     * @param {NodeList|Array|string} [options.toggleButtons] — buttons with data-review-mode
     * @param {NodeList|Array|string} [options.filters] — buttons with data-review-filter
     * @param {string|HTMLElement} [options.selection] — footer selection summary
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
        var selectionEl = queryEl(options.selection);
        var data = options.data || {};
        var points = data.review || [];
        var mode = options.defaultMode === "result" ? "result" : "pace";
        var filterMode = "all";
        var selectedAnswerId = null;

        if (!grid) return null;

        var toggleButtons = options.toggleButtons;
        if (typeof toggleButtons === "string") {
            toggleButtons = document.querySelectorAll(toggleButtons);
        }

        var filterButtons = options.filters;
        if (typeof filterButtons === "string") {
            filterButtons = document.querySelectorAll(filterButtons);
        }

        function showPace() {
            return mode === "pace";
        }

        function syncToggle() {
            if (toggleButtons) {
                Array.prototype.forEach.call(toggleButtons, function (btn) {
                    var active = btn.getAttribute("data-review-mode") === mode;
                    btn.classList.toggle("is-active", active);
                    btn.setAttribute("aria-pressed", active ? "true" : "false");
                });
            }
            if (legend) {
                legend.classList.toggle("answer-review__legend--result-only", !showPace());
            }
        }

        function syncFilters() {
            if (!filterButtons) return;
            Array.prototype.forEach.call(filterButtons, function (btn) {
                var active = btn.getAttribute("data-review-filter") === filterMode;
                btn.classList.toggle("is-active", active);
                btn.setAttribute("aria-pressed", active ? "true" : "false");
            });
        }

        function visibleEntries() {
            return points
                .map(function (point, index) {
                    return { point: point, index: index };
                })
                .filter(function (entry) {
                    if (filterMode === "missed") {
                        return !entry.point.is_correct || entry.point.unanswered;
                    }
                    return true;
                });
        }

        function updateSelection(point, index) {
            if (!selectionEl) return;
            var questionEl = selectionEl.querySelector("[data-review-selection-question]");
            var resultEl = selectionEl.querySelector("[data-review-selection-result]");
            var paceEl = selectionEl.querySelector("[data-review-selection-pace]");
            var openBtn = selectionEl.querySelector("[data-review-selection-open]");

            Array.prototype.forEach.call(
                grid.querySelectorAll(".answer-review__cell.is-selected"),
                function (cell) {
                    cell.classList.remove("is-selected");
                }
            );

            if (!point) {
                selectedAnswerId = null;
                if (questionEl) questionEl.textContent = "Select a question";
                if (resultEl) {
                    resultEl.textContent = "";
                    resultEl.className = "answer-review__selection-result";
                }
                if (paceEl) paceEl.textContent = "";
                if (openBtn) {
                    openBtn.disabled = true;
                    openBtn.removeAttribute("data-answer-id");
                }
                return;
            }

            selectedAnswerId = point.answer_id || null;
            if (questionEl) questionEl.textContent = "Question " + (point.label || index + 1);
            if (resultEl) {
                resultEl.textContent = resultLabel(point);
                resultEl.className =
                    "answer-review__selection-result " +
                    (point.unanswered
                        ? "is-unanswered"
                        : point.is_correct
                          ? "is-correct"
                          : "is-missed");
            }
            if (paceEl) {
                paceEl.textContent = point.unanswered
                    ? "No answer"
                    : paceLabel(point.pace) + " pace";
            }
            if (openBtn) {
                openBtn.disabled = !selectedAnswerId;
                if (selectedAnswerId) {
                    openBtn.setAttribute("data-answer-id", String(selectedAnswerId));
                } else {
                    openBtn.removeAttribute("data-answer-id");
                }
            }

            var cell = grid.querySelector(
                '.answer-review__cell[data-point-index="' + index + '"]'
            );
            if (cell) cell.classList.add("is-selected");
        }

        function openAnswer(answerId) {
            answerId = parseInt(answerId, 10);
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
        }

        function build() {
            syncToggle();
            syncFilters();

            if (!points.length) {
                grid.innerHTML = "";
                if (emptyEl) emptyEl.classList.remove("hidden");
                if (wrapEl) wrapEl.classList.add("hidden");
                updateSelection(null);
                return;
            }
            if (emptyEl) emptyEl.classList.add("hidden");
            if (wrapEl) wrapEl.classList.remove("hidden");

            var entries = visibleEntries();
            if (!entries.length) {
                grid.innerHTML =
                    '<p class="answer-review__filter-empty">No missed questions in this session.</p>';
                updateSelection(null);
                return;
            }

            var n = points.length;
            var size = Math.max(40, Math.min(56, Math.round(480 / Math.sqrt(n))));
            grid.style.setProperty("--answer-review-cell-size", size + "px");
            grid.setAttribute("data-mode", mode);
            grid.setAttribute("data-filter", filterMode);

            grid.innerHTML = entries
                .map(function (entry) {
                    var point = entry.point;
                    var index = entry.index;
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
                    var confidence = shortConfidence(point);
                    var confidenceHtml = confidence
                        ? '<span class="answer-review__cell-confidence">' +
                          confidence +
                          "</span>"
                        : "";
                    return (
                        '<button type="button" class="answer-review__cell ' +
                        borderCls +
                        '" data-answer-id="' +
                        (point.answer_id || "") +
                        '" data-point-index="' +
                        index +
                        '" title="' +
                        title +
                        '" aria-label="' +
                        title +
                        '" role="listitem">' +
                        '<span class="answer-review__cell-top">' +
                        '<span class="answer-review__cell-num">' +
                        (point.label || index + 1) +
                        "</span>" +
                        barsHtml +
                        "</span>" +
                        confidenceHtml +
                        "</button>"
                    );
                })
                .join("");

            var preferred = entries.filter(function (entry) {
                return entry.point.answer_id === selectedAnswerId;
            })[0];
            if (!preferred) {
                preferred = entries.filter(function (entry) {
                    return !entry.point.is_correct || entry.point.unanswered;
                })[0];
            }
            if (!preferred) preferred = entries[0];
            updateSelection(preferred.point, preferred.index);
        }

        grid.addEventListener("click", function (event) {
            if (options.clickable === false) return;
            var btn = event.target.closest(".answer-review__cell");
            if (!btn) return;
            updateSelection(
                points[parseInt(btn.getAttribute("data-point-index"), 10)],
                parseInt(btn.getAttribute("data-point-index"), 10)
            );
            openAnswer(btn.getAttribute("data-answer-id"));
        });

        grid.addEventListener("mouseover", function (event) {
            var btn = event.target.closest(".answer-review__cell");
            if (!btn) return;
            var index = parseInt(btn.getAttribute("data-point-index"), 10);
            updateSelection(points[index], index);
        });

        grid.addEventListener("focusin", function (event) {
            var btn = event.target.closest(".answer-review__cell");
            if (!btn) return;
            var index = parseInt(btn.getAttribute("data-point-index"), 10);
            updateSelection(points[index], index);
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

        if (filterButtons) {
            Array.prototype.forEach.call(filterButtons, function (btn) {
                btn.addEventListener("click", function () {
                    var next = btn.getAttribute("data-review-filter");
                    if (next !== "all" && next !== "missed") return;
                    filterMode = next;
                    build();
                });
            });
        }

        if (selectionEl) {
            var openBtn = selectionEl.querySelector("[data-review-selection-open]");
            if (openBtn) {
                openBtn.addEventListener("click", function () {
                    openAnswer(openBtn.getAttribute("data-answer-id"));
                });
            }
        }

        build();
        return { rebuild: build };
    }

    window.ExamiQUI = window.ExamiQUI || {};
    window.ExamiQUI.renderSessionAnswerReview = renderSessionAnswerReview;
})();
