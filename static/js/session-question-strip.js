/**
 * Session summary question heatmap strip (confidence 0–3 / mistakes 0–1).
 */
(function () {
    "use strict";

    var CONFIDENCE_CLASSES = {
        0: "confidence-tier-badge--none",
        1: "confidence-tier-badge--low",
        2: "confidence-tier-badge--average",
        3: "confidence-tier-badge--high",
    };

    var CONFIDENCE_LABELS = {
        0: "No ratings",
        1: "Guessing",
        2: "Not sure",
        3: "Sure",
    };

    function resolveEl(value) {
        if (!value) return null;
        return typeof value === "string" ? document.getElementById(value) : value;
    }

    function cellClass(metric, value) {
        if (metric === "mistakes") {
            return value ? "session-strip-cell--wrong" : "session-strip-cell--correct";
        }
        var key = Math.round(Number(value) || 0);
        if (key < 0) key = 0;
        if (key > 3) key = 3;
        return CONFIDENCE_CLASSES[key] || CONFIDENCE_CLASSES[0];
    }

    function cellTitle(metric, value, index) {
        if (metric === "mistakes") {
            return "Q" + index + ": " + (value ? "Wrong" : "Correct");
        }
        var key = Math.round(Number(value) || 0);
        return "Q" + index + ": " + (CONFIDENCE_LABELS[key] || "None") + " confidence";
    }

    function renderSessionQuestionStrip(options) {
        options = options || {};
        var grid = resolveEl(options.grid);
        var metricSelect = resolveEl(options.metricSelect);
        var legend = resolveEl(options.legend);
        var countEl = resolveEl(options.countEl);
        var emptyEl = resolveEl(options.emptyEl);
        var wrapEl = resolveEl(options.wrapEl);
        var data = options.data || {};
        var defaultMetric = options.defaultMetric || "confidence";

        if (!grid) return null;

        function currentMetric() {
            var metric = (metricSelect && metricSelect.value) || defaultMetric;
            if (metric !== "confidence" && metric !== "mistakes") {
                metric = defaultMetric;
            }
            return metric;
        }

        function pointsFor(metric) {
            return data[metric] || [];
        }

        function renderLegend(metric) {
            if (!legend) return;
            if (metric === "mistakes") {
                legend.innerHTML =
                    '<span class="session-strip-legend__item"><i class="session-strip-legend__swatch session-strip-cell--wrong"></i> Wrong</span>' +
                    '<span class="session-strip-legend__item"><i class="session-strip-legend__swatch session-strip-cell--correct"></i> Correct</span>';
                return;
            }
            legend.innerHTML =
                '<span class="session-strip-legend__item"><i class="session-strip-legend__swatch confidence-tier-badge--none"></i> None</span>' +
                '<span class="session-strip-legend__item"><i class="session-strip-legend__swatch confidence-tier-badge--low"></i> Low</span>' +
                '<span class="session-strip-legend__item"><i class="session-strip-legend__swatch confidence-tier-badge--average"></i> Average</span>' +
                '<span class="session-strip-legend__item"><i class="session-strip-legend__swatch confidence-tier-badge--high"></i> High</span>';
        }

        function build() {
            var metric = currentMetric();
            var points = pointsFor(metric);
            renderLegend(metric);

            if (countEl) {
                countEl.textContent = points.length
                    ? points.length + " question" + (points.length === 1 ? "" : "s")
                    : "";
            }

            if (!points.length) {
                grid.innerHTML = "";
                if (emptyEl) emptyEl.classList.remove("hidden");
                if (wrapEl) wrapEl.classList.add("hidden");
                return;
            }
            if (emptyEl) emptyEl.classList.add("hidden");
            if (wrapEl) wrapEl.classList.remove("hidden");

            // Scale cell size with question count (more questions → smaller cells).
            var n = points.length;
            var size = Math.max(28, Math.min(48, Math.round(420 / Math.sqrt(n))));
            grid.style.setProperty("--session-strip-cell-size", size + "px");
            grid.setAttribute("data-metric", metric);

            grid.innerHTML = points
                .map(function (point, index) {
                    var answerId = point.answer_id;
                    var value = point.value;
                    var cls = cellClass(metric, value);
                    var title = cellTitle(metric, value, index + 1);
                    return (
                        '<button type="button" class="session-strip-cell ' +
                        cls +
                        '" data-answer-id="' +
                        answerId +
                        '" title="' +
                        title +
                        '" aria-label="' +
                        title +
                        '">' +
                        (point.label || index + 1) +
                        "</button>"
                    );
                })
                .join("");
        }

        grid.addEventListener("click", function (event) {
            if (options.clickable === false) return;
            var btn = event.target.closest(".session-strip-cell");
            if (!btn) return;
            var answerId = parseInt(btn.getAttribute("data-answer-id"), 10);
            if (!answerId) return;

            // Faculty (and other callers) can navigate to a dedicated answer page.
            var template = options.answerUrlTemplate || "";
            if (template) {
                window.location.href = template
                    .replace("{id}", String(answerId))
                    .replace("{pk}", String(answerId))
                    .replace("/0/", "/" + answerId + "/");
                return;
            }

            // Students open the AI tutor review screen for that answer.
            if (!window.ExamiQTutor || !window.ExamiQTutor.open) return;
            window.ExamiQTutor.open({
                answerId: answerId,
                reviewMode: true,
                includeAll: true,
                screen: "solution",
            });
        });

        if (metricSelect) {
            metricSelect.addEventListener("change", build);
        }

        build();
        return { rebuild: build };
    }

    window.ExamiQUI = window.ExamiQUI || {};
    window.ExamiQUI.renderSessionQuestionStrip = renderSessionQuestionStrip;
})();
