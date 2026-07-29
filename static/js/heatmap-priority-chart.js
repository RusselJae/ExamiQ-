/**
 * Horizontal stacked bar chart for heatmap questions.
 * Sorted lowest-confidence-first; paginated (10 per page), controls centered.
 */
(function () {
    const PAGE_SIZE = 10;
    const ROW_PX = 32;
    const CHART_CHROME_PX = 96;
    const MIN_HEIGHT_PX = 260;

    const TIER_COLORS = {
        none: "#D32F2F",
        low: "#F57C00",
        average: "#FBC02D",
        high: "#388E3C",
    };

    function priorityScore(q) {
        const total = Math.max(q.total || 0, 1);
        const weak = (q.none || 0) + (q.low || 0);
        return weak / total;
    }

    function sortByLowestConfidence(questions) {
        return (questions || []).slice().sort(function (a, b) {
            const pa = priorityScore(a);
            const pb = priorityScore(b);
            if (pb !== pa) return pb - pa;
            const wa = (a.none || 0) + (a.low || 0);
            const wb = (b.none || 0) + (b.low || 0);
            if (wb !== wa) return wb - wa;
            return (a.question_id || 0) - (b.question_id || 0);
        });
    }

    function chartHeight(visibleCount) {
        return Math.max(MIN_HEIGHT_PX, visibleCount * ROW_PX + CHART_CHROME_PX);
    }

    function truncateStem(stem, max) {
        const text = (stem || "").trim();
        if (text.length <= max) return text;
        return text.slice(0, max - 1) + "…";
    }

    function resolveEl(value) {
        if (!value) return null;
        return typeof value === "string" ? document.getElementById(value) : value;
    }

    /**
     * @param {object} options
     * @param {HTMLCanvasElement|string} options.canvas
     * @param {HTMLElement|string} [options.wrapEl]
     * @param {HTMLElement|string} [options.prevBtn]
     * @param {HTMLElement|string} [options.nextBtn]
     * @param {HTMLElement|string} [options.pageLabel]
     * @param {HTMLElement|string} [options.statusEl]
     * @param {HTMLElement|string} [options.pagerEl]
     * @param {Array} options.questions
     * @param {number} [options.pageSize]
     */
    function renderHeatmapPriorityChart(options) {
        options = options || {};
        if (typeof Chart === "undefined") return null;

        const canvas = resolveEl(options.canvas);
        if (!canvas) return null;

        const wrapEl = resolveEl(options.wrapEl);
        const prevBtn = resolveEl(options.prevBtn);
        const nextBtn = resolveEl(options.nextBtn);
        const pageLabel = resolveEl(options.pageLabel);
        const statusEl = resolveEl(options.statusEl);
        const pagerEl = resolveEl(options.pagerEl);

        // Back-compat with Show more / Show less markup
        const moreBtn = resolveEl(options.moreBtn);
        const lessBtn = resolveEl(options.lessBtn);

        const pageSize = Math.max(10, options.pageSize || PAGE_SIZE);
        const sorted = sortByLowestConfidence(options.questions);
        if (!sorted.length) {
            if (wrapEl) wrapEl.classList.add("hidden");
            if (pagerEl) pagerEl.classList.add("hidden");
            return null;
        }

        const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
        let page = 1;
        let chart = null;

        function updateChrome() {
            const start = (page - 1) * pageSize + 1;
            const end = Math.min(page * pageSize, sorted.length);

            if (statusEl) {
                statusEl.textContent =
                    "Showing " +
                    start +
                    "–" +
                    end +
                    " of " +
                    sorted.length +
                    " questions (lowest confidence first)";
            }
            if (pageLabel) {
                pageLabel.textContent = "Page " + page + " of " + totalPages;
            }
            if (prevBtn) {
                prevBtn.disabled = page <= 1;
                prevBtn.setAttribute("aria-disabled", page <= 1 ? "true" : "false");
            }
            if (nextBtn) {
                nextBtn.disabled = page >= totalPages;
                nextBtn.setAttribute(
                    "aria-disabled",
                    page >= totalPages ? "true" : "false"
                );
            }
            if (pagerEl) {
                pagerEl.classList.toggle("hidden", totalPages <= 1);
            }
            if (moreBtn) {
                moreBtn.classList.toggle("hidden", page >= totalPages);
            }
            if (lessBtn) {
                lessBtn.classList.toggle("hidden", page <= 1);
            }
        }

        function buildChart() {
            const startIdx = (page - 1) * pageSize;
            const slice = sorted.slice(startIdx, startIdx + pageSize);
            if (wrapEl) {
                wrapEl.style.height = chartHeight(slice.length) + "px";
                wrapEl.classList.remove("hidden");
            }

            const labels = slice.map(function (q) {
                return "Q" + q.question_id;
            });
            const config = {
                type: "bar",
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: "No Confidence",
                            data: slice.map(function (q) {
                                return q.none || 0;
                            }),
                            backgroundColor: TIER_COLORS.none,
                            borderRadius: 2,
                        },
                        {
                            label: "Low Confidence",
                            data: slice.map(function (q) {
                                return q.low || 0;
                            }),
                            backgroundColor: TIER_COLORS.low,
                            borderRadius: 2,
                        },
                        {
                            label: "Average Confidence",
                            data: slice.map(function (q) {
                                return q.average || 0;
                            }),
                            backgroundColor: TIER_COLORS.average,
                            borderRadius: 2,
                        },
                        {
                            label: "High Confidence",
                            data: slice.map(function (q) {
                                return q.high || 0;
                            }),
                            backgroundColor: TIER_COLORS.high,
                            borderRadius: 2,
                        },
                    ],
                },
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            stacked: true,
                            beginAtZero: true,
                            ticks: { precision: 0 },
                            grid: { color: "#f1f5f9" },
                        },
                        y: {
                            stacked: true,
                            grid: { display: false },
                        },
                    },
                    plugins: {
                        legend: {
                            position: "bottom",
                            align: "center",
                        },
                        tooltip: {
                            callbacks: {
                                title: function (items) {
                                    const idx = items[0] && items[0].dataIndex;
                                    const q = slice[idx];
                                    if (!q) return "";
                                    return (
                                        "Q" +
                                        q.question_id +
                                        " · " +
                                        truncateStem(q.question_stem, 72)
                                    );
                                },
                            },
                        },
                    },
                },
            };

            if (chart) {
                chart.destroy();
            }
            chart = new Chart(canvas, config);
            updateChrome();
            return chart;
        }

        function goTo(nextPage) {
            page = Math.min(totalPages, Math.max(1, nextPage));
            buildChart();
        }

        if (prevBtn) {
            prevBtn.addEventListener("click", function () {
                goTo(page - 1);
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener("click", function () {
                goTo(page + 1);
            });
        }
        if (moreBtn) {
            moreBtn.addEventListener("click", function () {
                goTo(page + 1);
            });
        }
        if (lessBtn) {
            lessBtn.addEventListener("click", function () {
                goTo(page - 1);
            });
        }

        return buildChart();
    }

    window.ExamiQUI = window.ExamiQUI || {};
    window.ExamiQUI.HEATMAP_TIER_COLORS = TIER_COLORS;
    window.ExamiQUI.sortHeatmapQuestions = sortByLowestConfidence;
    window.ExamiQUI.renderHeatmapPriorityChart = renderHeatmapPriorityChart;
})();
