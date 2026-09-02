/**
 * Shared line chart for faculty overview + student trend pages.
 *
 * Faculty mode: data[range][metric] = [{label, value}, ...] with range select.
 * Flat mode: data[metric] = [{label, value}, ...] with optional pageSize pagination.
 */
(function () {
    "use strict";

    var DEFAULT_METRIC_LABELS = {
        students: "Students participating",
        scores: "Average score (out of 70)",
        confidence: "Confidence level (0–3)",
        mistakes: "Mistakes",
    };

    var DEFAULT_METRIC_COLORS = {
        students: "#1a4731",
        scores: "#2563eb",
        confidence: "#d97706",
        mistakes: "#dc2626",
    };

    var DEFAULT_Y_MAX = {
        scores: 70,
        confidence: 3,
    };

    function resolveEl(value) {
        if (!value) return null;
        return typeof value === "string" ? document.getElementById(value) : value;
    }

    function mergeMaps(base, extra) {
        var out = {};
        Object.keys(base).forEach(function (k) {
            out[k] = base[k];
        });
        if (extra) {
            Object.keys(extra).forEach(function (k) {
                out[k] = extra[k];
            });
        }
        return out;
    }

    function renderOverviewTrendsChart(options) {
        options = options || {};
        if (typeof Chart === "undefined") return null;

        var canvas = resolveEl(options.canvas);
        if (!canvas) return null;

        var metricSelect = resolveEl(options.metricSelect);
        var rangeSelect = resolveEl(options.rangeSelect);
        var pageLabelEl = resolveEl(options.pageLabel);
        var prevBtn = resolveEl(options.prevBtn);
        var nextBtn = resolveEl(options.nextBtn);
        var emptyEl = resolveEl(options.emptyEl);
        var wrapEl = resolveEl(options.wrapEl);

        var data = options.data || {};
        var flatMode = !!options.flatMode;
        var pageSize = options.pageSize || 0;
        var expectedStudents = options.expectedStudents || 0;
        var defaultMetric = options.defaultMetric || (flatMode ? "confidence" : "students");
        var metricLabels = mergeMaps(DEFAULT_METRIC_LABELS, options.metricLabels);
        var metricColors = mergeMaps(DEFAULT_METRIC_COLORS, options.metricColors);
        var yMaxByMetric = mergeMaps(DEFAULT_Y_MAX, options.yMaxByMetric);

        var pageIndex = 0;
        var chart = null;

        function metricKeys() {
            return Object.keys(metricLabels);
        }

        function resolveMetric() {
            var metric = (metricSelect && metricSelect.value) || defaultMetric;
            if (!metricLabels[metric]) {
                metric = defaultMetric;
                if (!metricLabels[metric]) {
                    metric = metricKeys()[0];
                }
            }
            return metric;
        }

        function fullPoints(metric) {
            if (flatMode) {
                return data[metric] || [];
            }
            var range = (rangeSelect && rangeSelect.value) || "weekly";
            if (!data[range]) range = "weekly";
            var bucket = data[range] || {};
            return bucket[metric] || [];
        }

        function currentSeries() {
            var metric = resolveMetric();
            var points = fullPoints(metric);
            var total = points.length;
            var start = 0;
            var end = total;

            if (pageSize > 0 && total > 0) {
                var maxPage = Math.max(0, Math.ceil(total / pageSize) - 1);
                if (pageIndex > maxPage) pageIndex = maxPage;
                if (pageIndex < 0) pageIndex = 0;
                start = pageIndex * pageSize;
                end = Math.min(start + pageSize, total);
                points = points.slice(start, end);
            }

            return {
                metric: metric,
                labels: points.map(function (p) {
                    return p.label;
                }),
                values: points.map(function (p) {
                    return p.value;
                }),
                studentCounts: points.map(function (p) {
                    return p.student_count != null ? p.student_count : null;
                }),
                total: total,
                start: start,
                end: end,
            };
        }

        function ySuggestedMax(metric, values) {
            if (yMaxByMetric[metric] != null) return yMaxByMetric[metric];
            var max = 0;
            values.forEach(function (v) {
                if (v > max) max = v;
            });
            if (metric === "students") {
                return Math.max(
                    expectedStudents || 1,
                    Math.ceil(max),
                    1
                );
            }
            if (metric === "mistakes") {
                return Math.max(1, Math.ceil(max));
            }
            return Math.max(3, Math.ceil(max * 1.15) || 3);
        }

        function usesIntegerTicks(metric) {
            return (
                metric === "students" ||
                metric === "scores" ||
                metric === "mistakes"
            );
        }

        function updatePager(series) {
            if (pageLabelEl) {
                if (!series.total) {
                    pageLabelEl.textContent = "No data";
                } else if (pageSize > 0) {
                    pageLabelEl.textContent =
                        series.start + 1 + "–" + series.end + " of " + series.total;
                } else {
                    pageLabelEl.textContent = series.total + " points";
                }
            }
            if (prevBtn) {
                prevBtn.disabled = pageSize <= 0 || series.start <= 0;
            }
            if (nextBtn) {
                nextBtn.disabled =
                    pageSize <= 0 || !series.total || series.end >= series.total;
            }
        }

        function setEmpty(isEmpty) {
            if (emptyEl) emptyEl.classList.toggle("hidden", !isEmpty);
            if (wrapEl) wrapEl.classList.toggle("hidden", isEmpty);
            if (canvas) canvas.classList.toggle("hidden", isEmpty);
        }

        function build() {
            var series = currentSeries();
            updatePager(series);

            if (!series.total) {
                setEmpty(true);
                if (chart) {
                    chart.destroy();
                    chart = null;
                }
                return null;
            }
            setEmpty(false);

            var color = metricColors[series.metric] || metricColors.students;
            var label = metricLabels[series.metric] || series.metric;
            var config = {
                type: "line",
                data: {
                    labels: series.labels,
                    datasets: [
                        {
                            label: label,
                            data: series.values,
                            studentCounts: series.studentCounts,
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
                        y: (function () {
                            var isConfidence = series.metric === "confidence";
                            var axis = {
                                beginAtZero: true,
                                ticks: {
                                    precision: usesIntegerTicks(series.metric) ? 0 : undefined,
                                    stepSize: usesIntegerTicks(series.metric) ? 1 : undefined,
                                },
                                grid: { color: "#f1f5f9" },
                                title: {
                                    display: true,
                                    text: label,
                                },
                            };
                            if (isConfidence) {
                                axis.min = 0;
                                axis.max = 3;
                                axis.ticks.stepSize = 1;
                            } else if (series.metric === "scores") {
                                axis.max = 70;
                                axis.ticks.stepSize = 5;
                            } else if (series.metric === "students") {
                                axis.max = ySuggestedMax(
                                    series.metric,
                                    series.values
                                );
                                axis.ticks.stepSize = 1;
                            } else {
                                axis.suggestedMax = ySuggestedMax(
                                    series.metric,
                                    series.values
                                );
                            }
                            return axis;
                        })(),
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                afterLabel: function (context) {
                                    var counts =
                                        context.dataset.studentCounts || [];
                                    var count = counts[context.dataIndex];
                                    if (
                                        (series.metric === "confidence" ||
                                            series.metric === "scores") &&
                                        count != null
                                    ) {
                                        var noun = count === 1 ? "student" : "students";
                                        return count + " " + noun;
                                    }
                                    return "";
                                },
                            },
                        },
                    },
                },
            };

            if (chart) chart.destroy();
            chart = new Chart(canvas, config);
            return chart;
        }

        if (metricSelect) {
            metricSelect.addEventListener("change", function () {
                pageIndex = 0;
                build();
            });
        }
        if (rangeSelect) {
            rangeSelect.addEventListener("change", function () {
                pageIndex = 0;
                build();
            });
        }
        if (prevBtn) {
            prevBtn.addEventListener("click", function () {
                pageIndex -= 1;
                build();
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener("click", function () {
                pageIndex += 1;
                build();
            });
        }

        return build();
    }

    window.ExamiQUI = window.ExamiQUI || {};
    window.ExamiQUI.renderOverviewTrendsChart = renderOverviewTrendsChart;
})();
