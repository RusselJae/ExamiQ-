/**
 * Student dashboard: mistakes per question.
 *
 * Mirrors the faculty "Mistakes per question" bar chart (single series,
 * rounded bars, integer y-axis, click-through to the answer detail) but drops
 * the faculty paging/metric controls — students get one simple view.
 */
(function () {
    "use strict";

    var BAR_COLOR = "#1a5634";
    var MAX_BARS = 20;
    var MOBILE_MAX_BARS = 10;
    var MOBILE_QUERY = "(max-width: 640px)";
    var chart = null;

    /**
     * Narrow screens only get half as many bars so the labels stay readable.
     */
    function maxBars() {
        if (window.matchMedia && window.matchMedia(MOBILE_QUERY).matches) {
            return MOBILE_MAX_BARS;
        }
        return MAX_BARS;
    }

    function truncate(text, max) {
        var value = (text || "").trim();
        return value.length > max ? value.slice(0, max - 1) + "…" : value;
    }

    /**
     * Open the AI Tutor on the clicked question so students can ask about the
     * mistake in place. Falls back to the answer detail page when the tutor
     * is unavailable (script not loaded, or the question has no answer yet).
     */
    function openMistakePoint(point) {
        if (!point) return;
        var tutor = window.ExamiQTutor;
        if (tutor && typeof tutor.open === "function" && point.answer_id) {
            tutor.open({
                sessionId: point.session_id || null,
                answerId: point.answer_id,
            });
            return;
        }
        if (point.url) window.location.href = point.url;
    }

    function renderStudentMistakesChart(opts) {
        var canvas = document.getElementById(opts.canvasId || "studentMistakesChart");
        var wrapEl = document.getElementById(opts.wrapEl || "studentMistakesWrap");
        var emptyEl = document.getElementById(opts.emptyEl || "student-mistakes-empty");
        var countEl = document.getElementById(opts.countEl || "student-mistakes-count");
        var dataEl = document.getElementById(opts.dataEl || "student-trends-data");
        if (!canvas || typeof Chart === "undefined") return null;

        var points = ((dataEl && JSON.parse(dataEl.textContent)) || {}).mistakes || [];
        points = points.filter(function (point) {
            return point && (point.value || 0) > 0;
        });
        points = points.slice(0, maxBars());

        if (countEl) {
            countEl.textContent = points.length
                ? points.length + " question" + (points.length === 1 ? "" : "s")
                : "";
        }

        if (!points.length) {
            if (wrapEl) wrapEl.hidden = true;
            if (emptyEl) emptyEl.classList.remove("hidden");
            return null;
        }
        if (wrapEl) wrapEl.hidden = false;
        if (emptyEl) emptyEl.classList.add("hidden");

        if (chart) {
            chart.destroy();
            chart = null;
        }
        chart = new Chart(canvas.getContext("2d"), {
            type: "bar",
            data: {
                labels: points.map(function (point) {
                    return point.label;
                }),
                datasets: [
                    {
                        label: "Times incorrect",
                        data: points.map(function (point) {
                            return point.value;
                        }),
                        backgroundColor: BAR_COLOR,
                        borderRadius: 4,
                        barPercentage: 0.7,
                        categoryPercentage: 0.8,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: {
                    padding: { top: 16 },
                },
                onClick: function (_event, elements) {
                    if (!elements || !elements.length) return;
                    openMistakePoint(points[elements[0].index]);
                },
                onHover: function (event, elements) {
                    var target = event.native && event.native.target;
                    if (!target || !target.style) return;
                    target.style.cursor =
                        elements && elements.length ? "pointer" : "default";
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { maxRotation: 0, minRotation: 0, autoSkip: false },
                    },
                    y: {
                        beginAtZero: true,
                        ticks: { precision: 0, stepSize: 1 },
                        grid: { color: "#f1f5f9" },
                        title: { display: true, text: "Times incorrect" },
                    },
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            title: function (items) {
                                var point = points[items[0].dataIndex] || {};
                                return truncate(point.title, 60);
                            },
                            label: function (ctx) {
                                var point = points[ctx.dataIndex] || {};
                                var times = ctx.parsed.y || 0;
                                return (
                                    times +
                                    " wrong answer" +
                                    (times === 1 ? "" : "s") +
                                    (point.question_id ? " · Q" + point.question_id : "") +
                                    " — click to ask the AI Tutor"
                                );
                            },
                        },
                    },
                },
            },
        });
        return chart;
    }

    window.ExamiQUI = window.ExamiQUI || {};
    window.ExamiQUI.renderStudentMistakesChart = renderStudentMistakesChart;

    document.addEventListener("DOMContentLoaded", function () {
        renderStudentMistakesChart({ dataEl: "student-trends-data" });
        // Re-draw when the viewport crosses the mobile breakpoint so the bar
        // count follows the layout.
        if (window.matchMedia) {
            var query = window.matchMedia(MOBILE_QUERY);
            var onChange = function () {
                renderStudentMistakesChart({ dataEl: "student-trends-data" });
            };
            if (query.addEventListener) {
                query.addEventListener("change", onChange);
            } else if (query.addListener) {
                query.addListener(onChange);
            }
        }
    });
})();
