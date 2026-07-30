/**
 * Professor overview line chart — one metric at a time, weekly/monthly/yearly.
 */
(function () {
    "use strict";

    var METRIC_LABELS = {
        students: "Students participating",
        scores: "Average scores (%)",
        confidence: "Confidence level (1–5)",
    };

    var METRIC_COLORS = {
        students: "#1a4731",
        scores: "#2563eb",
        confidence: "#d97706",
    };

    function resolveEl(value) {
        if (!value) return null;
        return typeof value === "string" ? document.getElementById(value) : value;
    }

    function renderOverviewTrendsChart(options) {
        options = options || {};
        if (typeof Chart === "undefined") return null;

        var canvas = resolveEl(options.canvas);
        if (!canvas) return null;

        var metricSelect = resolveEl(options.metricSelect);
        var rangeSelect = resolveEl(options.rangeSelect);
        var data = options.data || {};
        var chart = null;

        function currentSeries() {
            var metric = (metricSelect && metricSelect.value) || "students";
            var range = (rangeSelect && rangeSelect.value) || "weekly";
            if (!METRIC_LABELS[metric]) metric = "students";
            if (!data[range]) range = "weekly";
            var bucket = data[range] || {};
            var points = bucket[metric] || [];
            return {
                metric: metric,
                range: range,
                labels: points.map(function (p) {
                    return p.label;
                }),
                values: points.map(function (p) {
                    return p.value;
                }),
            };
        }

        function ySuggestedMax(metric, values) {
            if (metric === "scores") return 100;
            if (metric === "confidence") return 5;
            var max = 0;
            values.forEach(function (v) {
                if (v > max) max = v;
            });
            return Math.max(5, Math.ceil(max * 1.15) || 5);
        }

        function build() {
            var series = currentSeries();
            var color = METRIC_COLORS[series.metric] || METRIC_COLORS.students;
            var config = {
                type: "line",
                data: {
                    labels: series.labels,
                    datasets: [
                        {
                            label: METRIC_LABELS[series.metric],
                            data: series.values,
                            borderColor: color,
                            backgroundColor: color + "22",
                            fill: true,
                            tension: 0.3,
                            pointRadius: 3,
                            pointHoverRadius: 5,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            grid: { display: false },
                            title: { display: false },
                        },
                        y: {
                            beginAtZero: true,
                            suggestedMax: ySuggestedMax(series.metric, series.values),
                            ticks: { precision: series.metric === "scores" ? 0 : undefined },
                            grid: { color: "#f1f5f9" },
                            title: {
                                display: true,
                                text: METRIC_LABELS[series.metric],
                            },
                        },
                    },
                    plugins: {
                        legend: { display: false },
                    },
                },
            };

            if (chart) chart.destroy();
            chart = new Chart(canvas, config);
            return chart;
        }

        if (metricSelect) {
            metricSelect.addEventListener("change", build);
        }
        if (rangeSelect) {
            rangeSelect.addEventListener("change", build);
        }

        return build();
    }

    window.ExamiQUI = window.ExamiQUI || {};
    window.ExamiQUI.renderOverviewTrendsChart = renderOverviewTrendsChart;
})();
