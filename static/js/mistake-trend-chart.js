/**
 * Faculty dashboard "Over time" panel.
 *
 * Reads the "mistake_trend" series produced by
 * apps.analytics.services.professor_mistake_trend and renders two independent
 * line charts sharing one range control:
 *   - Students over time  -> student_count (students who sat an exam)
 *   - Mistakes over time  -> value (mistake records in the bucket)
 *
 * Each point carries { label, value, mistake_students, student_count }.
 */
(function () {
    "use strict";

    const EXAM_COLOR = "#1a5634";
    const MISTAKE_COLOR = "#D32F2F";

    const LINE_STYLE = {
        borderColor: "#1a5634",
        backgroundColor: "rgba(26, 86, 52, 0.08)",
        borderWidth: 2,
        pointRadius: 3,
        pointHoverRadius: 5,
        pointBackgroundColor: "#1a5634",
        pointBorderColor: "#fff",
        pointBorderWidth: 1.5,
        tension: 0.3,
        fill: true,
    };

    function resolveEl(value) {
        if (!value) return null;
        return typeof value === "string" ? document.getElementById(value) : value;
    }

    function pickRange(data, rangeSelect) {
        var range = (rangeSelect && rangeSelect.value) || "weekly";
        if (!data[range]) range = "weekly";
        return data[range] || {};
    }

    function renderOverTimeCharts(options) {
        options = options || {};
        if (typeof Chart === "undefined") return null;

        var studentsCanvas = resolveEl(options.studentsCanvas);
        var mistakesCanvas = resolveEl(options.mistakesCanvas);
        if (!studentsCanvas || !mistakesCanvas) return null;

        var rangeSelect = resolveEl(options.rangeSelect);
        var subtitleEl = resolveEl(options.subtitleEl);
        var data = options.data || {};
        var charts = { students: null, mistakes: null };

        function points() {
            var bucket = pickRange(data, rangeSelect);
            return bucket.mistake_trend || [];
        }

        function lineChart(canvas, series, values, options2) {
            var opts = options2 || {};
            return new Chart(canvas, {
                type: "line",
                data: {
                    labels: series.map(function (p) {
                        return p.label;
                    }),
                    datasets: [
                        {
                            label: opts.label,
                            data: values,
                            borderColor: opts.color,
                            backgroundColor: opts.fillColor,
                            borderWidth: LINE_STYLE.borderWidth,
                            pointRadius: LINE_STYLE.pointRadius,
                            pointHoverRadius: LINE_STYLE.pointHoverRadius,
                            pointBackgroundColor: opts.color,
                            pointBorderColor: LINE_STYLE.pointBorderColor,
                            pointBorderWidth: LINE_STYLE.pointBorderWidth,
                            tension: LINE_STYLE.tension,
                            fill: opts.fill,
                            borderCapStyle: "round",
                            borderJoinStyle: "round",
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: "index", intersect: false },
                    layout: { padding: { top: 12 } },
                    scales: {
                        x: {
                            grid: { display: false },
                            ticks: {
                                maxRotation: 0,
                                autoSkip: true,
                                maxTicksLimit: 8,
                                font: { size: 11 },
                            },
                        },
                        y: {
                            beginAtZero: true,
                            ticks: { precision: 0 },
                            grid: { color: "#f1f5f9" },
                            title: {
                                display: true,
                                text: opts.yTitle,
                            },
                        },
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: opts.tooltip || {},
                    },
                },
            });
        }

        function buildCharts() {
            var series = points();

            var studentValues = series.map(function (p) {
                return p.student_count || 0;
            });
            var mistakeValues = series.map(function (p) {
                return p.value || 0;
            });

            if (charts.students) charts.students.destroy();
            if (charts.mistakes) charts.mistakes.destroy();

            charts.students = lineChart(
                studentsCanvas,
                series,
                studentValues,
                {
                    label: "Students",
                    color: EXAM_COLOR,
                    fillColor: "rgba(26, 86, 52, 0.08)",
                    fill: true,
                    yTitle: "Students",
                    tooltip: {
                        callbacks: {
                            afterBody: function (items) {
                                if (!items || !items.length) return "";
                                var point = series[items[0].dataIndex];
                                if (!point) return "";
                                return "Mistakes logged: " + (point.value || 0);
                            },
                        },
                    },
                }
            );

            charts.mistakes = lineChart(
                mistakesCanvas,
                series,
                mistakeValues,
                {
                    label: "Mistakes",
                    color: MISTAKE_COLOR,
                    fillColor: "rgba(211, 47, 47, 0.08)",
                    fill: true,
                    yTitle: "Mistakes",
                    tooltip: {
                        callbacks: {
                            afterBody: function (items) {
                                if (!items || !items.length) return "";
                                var point = series[items[0].dataIndex];
                                if (!point) return "";
                                return "Students affected: " + (point.mistake_students || 0);
                            },
                        },
                    },
                }
            );

            return charts;
        }

        function syncSubtitle() {
            if (!subtitleEl) return;
            var range = (rangeSelect && rangeSelect.value) || "weekly";
            subtitleEl.textContent =
                "Students who took an exam and mistakes recorded (" + range + ").";
        }

        if (rangeSelect) {
            rangeSelect.addEventListener("change", function () {
                syncSubtitle();
                buildCharts();
            });
        }

        syncSubtitle();
        buildCharts();
        return charts;
    }

    // Kept under the historical name so existing wiring keeps working.
    window.ExamiQUI = window.ExamiQUI || {};
    window.ExamiQUI.renderMistakeTrendChart = renderOverTimeCharts;
    window.ExamiQUI.renderOverTimeCharts = renderOverTimeCharts;
})();