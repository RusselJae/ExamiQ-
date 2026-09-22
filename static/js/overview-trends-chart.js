/**
 * Shared trends chart for faculty overview + student dashboard.
 *
 * Confidence metric: stacked Sure / Not sure / Guessing / No ratings bars
 * plus an "Answered correctly" line (0–100%).
 * Other metrics: existing filled line chart.
 */
(function () {
    "use strict";

    var DEFAULT_METRIC_LABELS = {
        students: "Students participating",
        scores: "Average score (out of 70)",
        confidence: "Confidence share (%)",
        mistakes: "Mistakes",
    };

    var DEFAULT_METRIC_COLORS = {
        students: "#1a5634",
        scores: "#1a5634",
        confidence: "#1a5634",
        mistakes: "#1a5634",
    };

    var STACK_COLORS = {
        sure: "#0f172a",
        not_sure: "#64748b",
        guessing: "#cbd5e1",
        none: "rgba(148, 163, 184, 0.15)",
        correct: "#1a5634",
    };

    var DEFAULT_Y_MAX = {
        scores: 70,
        confidence: 100,
    };

    /** Olive stroke with a thicker white underlay for a halo outline. */
    function outlinedLinePair(opts) {
        var data = opts.data;
        var color = opts.borderColor;
        var borderWidth = opts.borderWidth != null ? opts.borderWidth : 2.5;
        var tension = opts.tension != null ? opts.tension : 0.3;
        var order = opts.order != null ? opts.order : 1;
        var underlay = {
            type: "line",
            label: "",
            data: data,
            borderColor: "#ffffff",
            backgroundColor: "transparent",
            borderWidth: borderWidth + 3,
            pointRadius: 0,
            pointHoverRadius: 0,
            fill: false,
            tension: tension,
            order: order + 1,
            stack: false,
        };
        var overlay = {
            type: "line",
            label: opts.label,
            data: data,
            borderColor: color,
            backgroundColor:
                opts.backgroundColor != null ? opts.backgroundColor : "#fff",
            pointBackgroundColor: "#fff",
            pointBorderColor: color,
            pointBorderWidth: 2,
            borderWidth: borderWidth,
            pointRadius: opts.pointRadius != null ? opts.pointRadius : 5,
            pointHoverRadius: opts.pointHoverRadius != null ? opts.pointHoverRadius : 6,
            fill: !!opts.fill,
            tension: tension,
            order: order,
            stack: false,
        };
        if (opts.yAxisID) {
            underlay.yAxisID = opts.yAxisID;
            overlay.yAxisID = opts.yAxisID;
        }
        if (opts.studentCounts) {
            overlay.studentCounts = opts.studentCounts;
        }
        return [underlay, overlay];
    }

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

    function isStackedConfidencePoint(point) {
        return (
            point &&
            (point.sure != null ||
                point.not_sure != null ||
                point.guessing != null ||
                point.none != null)
        );
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
        var insightEl = resolveEl(options.insightEl);

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

        function resolveInsight(metric) {
            if (metric !== "confidence") return "";
            if (flatMode) {
                return data.confidence_insight || "";
            }
            var range = (rangeSelect && rangeSelect.value) || "weekly";
            var bucket = data[range] || {};
            return bucket.confidence_insight || "";
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
                points: points,
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
                stacked: metric === "confidence" && points.some(isStackedConfidencePoint),
            };
        }

        function ySuggestedMax(metric, values) {
            if (yMaxByMetric[metric] != null) return yMaxByMetric[metric];
            var max = 0;
            values.forEach(function (v) {
                if (v > max) max = v;
            });
            if (metric === "students") {
                return Math.max(expectedStudents || 1, Math.ceil(max), 1);
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

        function updateInsight(series) {
            if (!insightEl) return;
            var text = resolveInsight(series.metric);
            if (series.metric === "confidence" && text) {
                insightEl.hidden = false;
                var body = insightEl.querySelector("[data-confidence-insight-body]");
                if (body) body.textContent = text;
                else insightEl.textContent = text;
            } else {
                insightEl.hidden = true;
            }
        }

        function stackedDatasets(points) {
            return [
                {
                    type: "bar",
                    label: "Sure",
                    data: points.map(function (p) {
                        return p.sure || 0;
                    }),
                    backgroundColor: STACK_COLORS.sure,
                    borderWidth: 0,
                    stack: "confidence",
                    order: 2,
                    barPercentage: 0.65,
                    categoryPercentage: 0.8,
                },
                {
                    type: "bar",
                    label: "Not sure",
                    data: points.map(function (p) {
                        return p.not_sure || 0;
                    }),
                    backgroundColor: STACK_COLORS.not_sure,
                    borderWidth: 0,
                    stack: "confidence",
                    order: 2,
                    barPercentage: 0.65,
                    categoryPercentage: 0.8,
                },
                {
                    type: "bar",
                    label: "Guessing",
                    data: points.map(function (p) {
                        return p.guessing || 0;
                    }),
                    backgroundColor: STACK_COLORS.guessing,
                    borderWidth: 0,
                    stack: "confidence",
                    order: 2,
                    barPercentage: 0.65,
                    categoryPercentage: 0.8,
                },
                {
                    type: "bar",
                    label: "No ratings",
                    data: points.map(function (p) {
                        return p.none || 0;
                    }),
                    backgroundColor: STACK_COLORS.none,
                    borderColor: "#cbd5e1",
                    borderWidth: 1,
                    borderDash: [4, 3],
                    stack: "confidence",
                    order: 2,
                    barPercentage: 0.65,
                    categoryPercentage: 0.8,
                },
            ].concat(
                outlinedLinePair({
                    label: "Answered correctly",
                    data: points.map(function (p) {
                        return p.correct_pct != null ? p.correct_pct : null;
                    }),
                    borderColor: STACK_COLORS.correct,
                    backgroundColor: "#fff",
                    borderWidth: 2.5,
                    tension: 0.25,
                    order: 1,
                    yAxisID: "y1",
                })
            );
        }

        function build() {
            var series = currentSeries();
            updatePager(series);
            updateInsight(series);

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
            var config;

            if (series.stacked) {
                config = {
                    type: "bar",
                    data: {
                        labels: series.labels,
                        datasets: stackedDatasets(series.points),
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            x: {
                                stacked: true,
                                grid: { display: false },
                            },
                            y: {
                                stacked: true,
                                min: 0,
                                max: 100,
                                beginAtZero: true,
                                ticks: {
                                    stepSize: 25,
                                    callback: function (value) {
                                        return value + "%";
                                    },
                                },
                                grid: { color: "#f1f5f9" },
                                title: {
                                    display: true,
                                    text: "Share of answers",
                                },
                            },
                            y1: {
                                stacked: false,
                                min: 0,
                                max: 100,
                                display: false,
                                grid: { drawOnChartArea: false },
                            },
                        },
                        plugins: {
                            legend: {
                                display: true,
                                position: "top",
                                align: "start",
                                labels: {
                                    boxWidth: 12,
                                    boxHeight: 12,
                                    usePointStyle: true,
                                    pointStyle: "rectRounded",
                                    color: "#475569",
                                    font: { size: 12, weight: "600" },
                                    filter: function (item) {
                                        return !!item.text;
                                    },
                                },
                            },
                            tooltip: {
                                filter: function (context) {
                                    return !!context.dataset.label;
                                },
                                callbacks: {
                                    label: function (context) {
                                        var v = context.parsed.y;
                                        if (v == null) return context.dataset.label;
                                        return (
                                            context.dataset.label +
                                            ": " +
                                            Math.round(v) +
                                            "%"
                                        );
                                    },
                                },
                            },
                        },
                    },
                };
            } else {
                config = {
                    type: "line",
                    data: {
                        labels: series.labels,
                        datasets: outlinedLinePair({
                            label: label,
                            data: series.values,
                            studentCounts: series.studentCounts,
                            borderColor: color,
                            backgroundColor: color + "22",
                            borderWidth: 2.5,
                            fill: true,
                            tension: 0.3,
                        }),
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
                                var axis = {
                                    beginAtZero: true,
                                    ticks: {
                                        precision: usesIntegerTicks(series.metric)
                                            ? 0
                                            : undefined,
                                        stepSize: usesIntegerTicks(series.metric)
                                            ? 1
                                            : undefined,
                                    },
                                    grid: { color: "#f1f5f9" },
                                    title: {
                                        display: true,
                                        text: label,
                                    },
                                };
                                if (series.metric === "scores") {
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
                            legend: {
                                display: true,
                                position: "top",
                                align: "end",
                                labels: {
                                    boxWidth: 10,
                                    boxHeight: 10,
                                    usePointStyle: true,
                                    pointStyle: "circle",
                                    color: "#475569",
                                    font: { size: 12, weight: "600" },
                                    filter: function (item) {
                                        return !!item.text;
                                    },
                                },
                            },
                            tooltip: {
                                filter: function (context) {
                                    return !!context.dataset.label;
                                },
                                callbacks: {
                                    afterLabel: function (context) {
                                        var counts =
                                            context.dataset.studentCounts || [];
                                        var count = counts[context.dataIndex];
                                        if (
                                            series.metric === "scores" &&
                                            count != null
                                        ) {
                                            var noun =
                                                count === 1 ? "student" : "students";
                                            return count + " " + noun;
                                        }
                                        return "";
                                    },
                                },
                            },
                        },
                    },
                };
            }

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
