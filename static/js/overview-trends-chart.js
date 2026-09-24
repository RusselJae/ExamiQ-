/**
 * Shared trends chart for faculty overview + student dashboard.
 *
 * Confidence metric: dual-line Sure % vs Correct % with a filled gap
 * (overconfidence / underconfidence). Other metrics: filled line chart.
 */
(function () {
    "use strict";

    var DEFAULT_METRIC_LABELS = {
        students: "Students participating",
        scores: "Average score (out of 70)",
        confidence: "Sure vs correct (%)",
        sure: "Sure (%)",
        guessing: "Guessing (%)",
        mistakes: "Mistakes",
    };

    var DEFAULT_METRIC_COLORS = {
        students: "#1a5634",
        scores: "#1a5634",
        confidence: "#1a5634",
        sure: "#0284c7",
        guessing: "#94a3b8",
        mistakes: "#1a5634",
    };

    var SURE_CORRECT_COLORS = {
        sure: "#0284c7",
        correct: "#1a5634",
        overFill: "rgba(251, 146, 60, 0.22)",
        underFill: "rgba(16, 185, 129, 0.18)",
        overLabel: "#9a3412",
        underLabel: "#047857",
        gapClose: 15,
    };

    var DEFAULT_Y_MAX = {
        scores: 70,
        confidence: 100,
        sure: 100,
        guessing: 100,
    };

    var TITLE_BY_METRIC = {
        students: {
            title: "Students over time",
            subtitle: "How many students participated in each period.",
        },
        confidence: {
            title: "Feeling sure vs. being right",
            subtitle:
                "How often answers were marked Sure compared with how often they were correct.",
        },
        sure: {
            title: "Sure over time",
            subtitle: "Share of answers marked Sure in each period.",
        },
        guessing: {
            title: "Guessing over time",
            subtitle: "Share of answers marked Guessing in each period.",
        },
        mistakes: {
            title: "Mistakes per question",
            subtitle:
                "Questions with the most unique students who answered incorrectly.",
        },
    };

    var LEGEND_STYLE = {
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
    };

    /** Olive stroke with a thicker white underlay for a halo outline. */
    function outlinedLinePair(opts) {
        var data = opts.data;
        var color = opts.borderColor;
        var borderWidth = opts.borderWidth != null ? opts.borderWidth : 2.5;
        var tension = opts.tension != null ? opts.tension : 0.3;
        var order = opts.order != null ? opts.order : 1;
        // Do not set dataset.stack — Chart.js treats `stack: false` as the
        // stack id "false" and sums series, which mis-plots Correct %.
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
            borderDash: opts.borderDash || [],
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
            pointHoverRadius:
                opts.pointHoverRadius != null ? opts.pointHoverRadius : 6,
            fill: !!opts.fill,
            tension: tension,
            order: order,
            borderDash: opts.borderDash || [],
        };
        if (opts.yAxisID) {
            underlay.yAxisID = opts.yAxisID;
            overlay.yAxisID = opts.yAxisID;
        }
        if (opts.studentCounts) {
            overlay.studentCounts = opts.studentCounts;
        }
        if (opts.datasetId) {
            overlay.datasetId = opts.datasetId;
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

    function isSureCorrectPoint(point) {
        return (
            point &&
            (point.sure != null || point.correct_pct != null)
        );
    }

    function confidenceGap(point) {
        if (!point || point.correct_pct == null || point.sure == null) return null;
        // Align with chart lines: Sure % vs Correct % (not a diluted score).
        return point.correct_pct - point.sure;
    }

    function ratedWeight(point) {
        if (!point) return 0;
        return (point.sure || 0) + (point.not_sure || 0) + (point.guessing || 0);
    }

    function isActiveConfidencePoint(point) {
        if (!point || point.correct_pct == null || point.sure == null) return false;
        return ratedWeight(point) > 0;
    }

    /** Rated-share-weighted averages so busy Sure weeks aren't diluted by sparse ones. */
    function weightedSureCorrect(points) {
        var sureSum = 0;
        var correctSum = 0;
        var weightSum = 0;
        points.forEach(function (p) {
            if (!isActiveConfidencePoint(p)) return;
            var w = ratedWeight(p);
            sureSum += p.sure * w;
            correctSum += p.correct_pct * w;
            weightSum += w;
        });
        if (!weightSum) return null;
        return {
            sure: sureSum / weightSum,
            correct: correctSum / weightSum,
        };
    }

    function avgSurePct(points) {
        var agg = weightedSureCorrect(points);
        return agg ? agg.sure : null;
    }

    function avgCorrectPct(points) {
        var agg = weightedSureCorrect(points);
        return agg ? agg.correct : null;
    }

    function avgConfidenceGap(points) {
        var agg = weightedSureCorrect(points);
        if (!agg) return 0;
        return agg.correct - agg.sure;
    }

    function gapKind(points) {
        var gap = avgConfidenceGap(points);
        if (gap < -SURE_CORRECT_COLORS.gapClose) return "over";
        if (gap > SURE_CORRECT_COLORS.gapClose) return "under";
        return "realistic";
    }

    function gapStatusCopy(points) {
        var agg = weightedSureCorrect(points);
        if (!agg) {
            return { kind: "realistic", label: "Realistic", detail: "" };
        }
        var sure = agg.sure;
        var correct = agg.correct;
        var gap = correct - sure;
        var sureR = Math.round(sure);
        var correctR = Math.round(correct);
        var gapR = Math.round(Math.abs(gap));
        var kind =
            gap < -SURE_CORRECT_COLORS.gapClose
                ? "over"
                : gap > SURE_CORRECT_COLORS.gapClose
                  ? "under"
                  : "realistic";
        if (kind === "over") {
            return {
                kind: "over",
                label: "Overconfident",
                detail:
                    "Across this range, Sure (~" +
                    sureR +
                    "%) ran ahead of accuracy (~" +
                    correctR +
                    "%) by about " +
                    gapR +
                    " points.",
            };
        }
        if (kind === "under") {
            return {
                kind: "under",
                label: "Underconfident",
                detail:
                    "Across this range, accuracy (~" +
                    correctR +
                    "%) exceeded Sure (~" +
                    sureR +
                    "%) by about " +
                    gapR +
                    " points.",
            };
        }
        return {
            kind: "realistic",
            label: "Realistic",
            detail:
                "Across this range, Sure (~" +
                sureR +
                "%) closely matched accuracy (~" +
                correctR +
                "%).",
        };
    }

    function avgGap(points) {
        return -avgConfidenceGap(points);
    }

    /** Fill between Sure and Correct + end labels + center gap annotation. */
    var sureCorrectGapPlugin = {
        id: "sureCorrectGap",
        afterDatasetsDraw: function (chart) {
            var meta = chart.options.plugins && chart.options.plugins.sureCorrectGap;
            if (!meta || !meta.enabled) return;

            var sureDs = null;
            var correctDs = null;
            chart.data.datasets.forEach(function (ds, i) {
                if (ds.datasetId === "sure") sureDs = chart.getDatasetMeta(i);
                if (ds.datasetId === "correct") correctDs = chart.getDatasetMeta(i);
            });
            if (!sureDs || !correctDs || !sureDs.data.length) return;

            var ctx = chart.ctx;
            var points = meta.points || [];
            var n = sureDs.data.length;

            // Segment fills
            for (var i = 0; i < n - 1; i++) {
                var s0 = sureDs.data[i];
                var s1 = sureDs.data[i + 1];
                var c0 = correctDs.data[i];
                var c1 = correctDs.data[i + 1];
                if (!s0 || !s1 || !c0 || !c1) continue;
                if (s0.skip || s1.skip || c0.skip || c1.skip) continue;

                var sure0 = points[i] && points[i].sure != null ? points[i].sure : null;
                var sure1 =
                    points[i + 1] && points[i + 1].sure != null
                        ? points[i + 1].sure
                        : null;
                var cor0 =
                    points[i] && points[i].correct_pct != null
                        ? points[i].correct_pct
                        : null;
                var cor1 =
                    points[i + 1] && points[i + 1].correct_pct != null
                        ? points[i + 1].correct_pct
                        : null;
                if (sure0 == null || sure1 == null || cor0 == null || cor1 == null) {
                    continue;
                }

                var midGap = (sure0 + sure1) / 2 - (cor0 + cor1) / 2;
                if (Math.abs(midGap) < 0.5) continue;

                ctx.save();
                ctx.beginPath();
                ctx.moveTo(s0.x, s0.y);
                ctx.lineTo(s1.x, s1.y);
                ctx.lineTo(c1.x, c1.y);
                ctx.lineTo(c0.x, c0.y);
                ctx.closePath();
                ctx.fillStyle =
                    midGap > 0
                        ? SURE_CORRECT_COLORS.overFill
                        : SURE_CORRECT_COLORS.underFill;
                ctx.fill();
                ctx.restore();
            }

            // Center gap label removed — shown as status chip outside the chart.

            // End-of-series value labels
            var last = n - 1;
            var sLast = sureDs.data[last];
            var cLast = correctDs.data[last];
            var pLast = points[last];
            if (!sLast || !cLast || !pLast) return;

            ctx.save();
            ctx.font = "700 12px Inter, system-ui, sans-serif";
            ctx.textAlign = "left";
            ctx.textBaseline = "middle";

            var sureVal =
                pLast.sure != null ? Math.round(pLast.sure) + "%" : "";
            var correctVal =
                pLast.correct_pct != null
                    ? Math.round(pLast.correct_pct) + "%"
                    : "";

            if (sureVal && !sLast.skip) {
                ctx.fillStyle = SURE_CORRECT_COLORS.sure;
                ctx.fillText("Sure " + sureVal, sLast.x + 10, sLast.y);
            }
            if (correctVal && !cLast.skip) {
                ctx.fillStyle = SURE_CORRECT_COLORS.correct;
                var cy = cLast.y;
                if (Math.abs(cLast.y - sLast.y) < 14) {
                    cy = cLast.y > sLast.y ? cLast.y + 12 : cLast.y - 12;
                }
                ctx.fillText("Correct " + correctVal, cLast.x + 10, cy);
            }
            ctx.restore();
        },
    };

    function sureCorrectDatasets(points) {
        var sureData = points.map(function (p) {
            return p.sure != null ? p.sure : null;
        });
        var guessingData = points.map(function (p) {
            return p.guessing != null ? p.guessing : null;
        });
        var correctData = points.map(function (p) {
            return p.correct_pct != null ? p.correct_pct : null;
        });

        return [
            {
                type: "line",
                label: "Sure",
                datasetId: "sure",
                data: sureData,
                borderColor: SURE_CORRECT_COLORS.sure,
                backgroundColor: "#fff",
                pointBackgroundColor: "#fff",
                pointBorderColor: SURE_CORRECT_COLORS.sure,
                pointBorderWidth: 2,
                borderWidth: 2.5,
                pointRadius: 5,
                pointHoverRadius: 6,
                fill: false,
                tension: 0.25,
                order: 1,
            },
            {
                type: "line",
                label: "Guessing",
                datasetId: "guessing",
                data: guessingData,
                borderColor: "#94a3b8",
                backgroundColor: "#fff",
                pointBackgroundColor: "#fff",
                pointBorderColor: "#94a3b8",
                pointBorderWidth: 2,
                borderWidth: 2,
                borderDash: [4, 3],
                pointRadius: 4,
                pointHoverRadius: 5,
                fill: false,
                tension: 0.25,
                order: 2,
            },
            {
                type: "line",
                label: "Correct",
                datasetId: "correct",
                data: correctData,
                borderColor: SURE_CORRECT_COLORS.correct,
                backgroundColor: "#fff",
                pointBackgroundColor: "#fff",
                pointBorderColor: SURE_CORRECT_COLORS.correct,
                pointBorderWidth: 2,
                borderWidth: 2.5,
                borderDash: [6, 4],
                pointRadius: 5,
                pointHoverRadius: 6,
                fill: false,
                tension: 0.25,
                order: 1,
            },
        ];
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
        var titleEl = resolveEl(options.titleEl);
        var subtitleEl = resolveEl(options.subtitleEl);
        var gapStatusEl = resolveEl(options.gapStatusEl);

        var data = options.data || {};
        var flatMode = !!options.flatMode;
        var pageSize = options.pageSize || 0;
        var expectedStudents = options.expectedStudents || 0;
        var defaultMetric =
            options.defaultMetric || (flatMode ? "confidence" : "students");
        var metricLabels = mergeMaps(DEFAULT_METRIC_LABELS, options.metricLabels);
        var metricColors = mergeMaps(DEFAULT_METRIC_COLORS, options.metricColors);
        var yMaxByMetric = mergeMaps(DEFAULT_Y_MAX, options.yMaxByMetric);
        var titleMap = mergeMaps(TITLE_BY_METRIC, options.titleByMetric);

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
            if (metric === "sure" || metric === "guessing") {
                var confPoints = fullPoints("confidence");
                return confPoints.map(function (p) {
                    return {
                        label: p.label,
                        value:
                            metric === "sure"
                                ? p.sure != null
                                    ? p.sure
                                    : 0
                                : p.guessing != null
                                  ? p.guessing
                                  : 0,
                        sure: p.sure,
                        guessing: p.guessing,
                        not_sure: p.not_sure,
                        correct_pct: p.correct_pct,
                    };
                });
            }
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

        function updateTitles(metric) {
            var copy = titleMap[metric];
            if (!copy) return;
            if (titleEl) titleEl.textContent = copy.title;
            if (subtitleEl) subtitleEl.textContent = copy.subtitle;
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
                sureCorrect:
                    metric === "confidence" &&
                    points.some(isSureCorrectPoint),
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

        function updateGapStatus(series) {
            if (!gapStatusEl) return;
            if (series.metric !== "confidence" || !series.points.length) {
                gapStatusEl.hidden = true;
                gapStatusEl.innerHTML = "";
                gapStatusEl.className = "overview-gap-status-row";
                return;
            }
            var copy = gapStatusCopy(series.points);
            gapStatusEl.hidden = false;
            gapStatusEl.className =
                "overview-gap-status-row overview-gap-status-row--" + copy.kind;
            gapStatusEl.innerHTML =
                '<span class="overview-gap-status overview-gap-status--' +
                copy.kind +
                '">' +
                copy.label +
                "</span>" +
                (copy.detail
                    ? '<span class="overview-gap-status__detail">' +
                      copy.detail +
                      "</span>"
                    : "");
        }

        function updateInsight(series) {
            if (insightEl) insightEl.hidden = true;
            updateGapStatus(series);
        }

        function build() {
            var series = currentSeries();
            updatePager(series);
            updateInsight(series);
            updateTitles(series.metric);

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

            if (series.sureCorrect) {
                config = {
                    type: "line",
                    data: {
                        labels: series.labels,
                        datasets: sureCorrectDatasets(series.points),
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        layout: {
                            padding: { top: 16, right: 88 },
                        },
                        scales: {
                            x: {
                                grid: { display: false },
                            },
                            y: {
                                stacked: false,
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
                                    display: false,
                                },
                            },
                        },
                        plugins: {
                            legend: LEGEND_STYLE,
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
                            sureCorrectGap: {
                                enabled: true,
                                points: series.points,
                            },
                        },
                    },
                    plugins: [sureCorrectGapPlugin],
                };
            } else if (series.metric === "mistakes") {
                config = {
                    type: "bar",
                    data: {
                        labels: series.labels,
                        datasets: [
                            {
                                label: label,
                                data: series.values,
                                backgroundColor: "#1a5634",
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
                        scales: {
                            x: {
                                grid: { display: false },
                                ticks: {
                                    maxRotation: 45,
                                    minRotation: 0,
                                    autoSkip: true,
                                    maxTicksLimit: 12,
                                },
                            },
                            y: {
                                beginAtZero: true,
                                suggestedMax: ySuggestedMax(
                                    series.metric,
                                    series.values
                                ),
                                ticks: {
                                    precision: 0,
                                    stepSize: 1,
                                },
                                grid: { color: "#f1f5f9" },
                                title: {
                                    display: true,
                                    text: label,
                                },
                            },
                        },
                        plugins: {
                            legend: LEGEND_STYLE,
                            tooltip: {
                                callbacks: {
                                    label: function (context) {
                                        var v = context.parsed.y;
                                        return context.dataset.label + ": " + v;
                                    },
                                },
                            },
                            sureCorrectGap: { enabled: false },
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
                        layout: {
                            padding: { top: 16 },
                        },
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
                                } else if (
                                    series.metric === "sure" ||
                                    series.metric === "guessing"
                                ) {
                                    axis.max = 100;
                                    axis.ticks.stepSize = 25;
                                    axis.ticks.callback = function (value) {
                                        return value + "%";
                                    };
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
                            legend: LEGEND_STYLE,
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
                            sureCorrectGap: { enabled: false },
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
