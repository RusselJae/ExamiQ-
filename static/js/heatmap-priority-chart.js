/**
 * Vertical bar chart for heatmap questions.
 * Confidence mode: stacked tiers. Mistakes mode: mistake counts.
 * Paginated (10 per page), questions on X, metric on Y.
 */
(function () {
    const PAGE_SIZE = 10;
    const COL_PX = 56;
    const CHART_CHROME_PX = 120;
    const MIN_HEIGHT_PX = 320;
    const MISTAKE_COLOR = "#D32F2F";

    const TIER_COLORS = {
        none: "#D32F2F",
        low: "#F57C00",
        average: "#FBC02D",
        high: "#388E3C",
    };

    function sortByQuestionNumber(questions) {
        return (questions || []).slice().sort(function (a, b) {
            var na = a.q_number || 0;
            var nb = b.q_number || 0;
            if (na !== nb) return na - nb;
            return (a.question_id || 0) - (b.question_id || 0);
        });
    }

    function questionLabel(q) {
        if (q && q.q_label) return q.q_label;
        if (q && q.q_number) return "Q" + q.q_number;
        return "Q?";
    }

    function chartHeight(visibleCount) {
        return Math.max(MIN_HEIGHT_PX, Math.min(420, visibleCount * 8 + CHART_CHROME_PX));
    }

    function chartMinWidth(visibleCount) {
        return Math.max(480, visibleCount * COL_PX + 80);
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
     * @param {HTMLSelectElement|string} [options.metricSelect]
     * @param {Array} options.questions
     * @param {number} [options.pageSize]
     * @param {string} [options.metric] confidence | mistakes
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
        const metricSelect = resolveEl(options.metricSelect);
        const moreBtn = resolveEl(options.moreBtn);
        const lessBtn = resolveEl(options.lessBtn);

        const pageSize = Math.max(10, options.pageSize || PAGE_SIZE);
        let metric =
            (metricSelect && metricSelect.value) ||
            options.metric ||
            "confidence";
        if (metric !== "mistakes") metric = "confidence";

        function sortedQuestions() {
            return sortByQuestionNumber(options.questions);
        }

        let sorted = sortedQuestions();
        if (!sorted.length) {
            if (wrapEl) wrapEl.classList.add("hidden");
            if (pagerEl) pagerEl.classList.add("hidden");
            return null;
        }

        let totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
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
                    " questions (Q1 → Qn)";
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

        function confidenceDatasets(slice) {
            return [
                {
                    label: "No ratings",
                    data: slice.map(function (q) {
                        return q.none || 0;
                    }),
                    backgroundColor: TIER_COLORS.none,
                    borderRadius: 2,
                },
                {
                    label: "Guessing",
                    data: slice.map(function (q) {
                        return q.low || 0;
                    }),
                    backgroundColor: TIER_COLORS.low,
                    borderRadius: 2,
                },
                {
                    label: "Not sure",
                    data: slice.map(function (q) {
                        return q.average || 0;
                    }),
                    backgroundColor: TIER_COLORS.average,
                    borderRadius: 2,
                },
                {
                    label: "Sure",
                    data: slice.map(function (q) {
                        return q.high || 0;
                    }),
                    backgroundColor: TIER_COLORS.high,
                    borderRadius: 2,
                },
            ];
        }

        function mistakesDatasets(slice) {
            return [
                {
                    label: "Mistakes",
                    data: slice.map(function (q) {
                        return q.mistakes || 0;
                    }),
                    backgroundColor: MISTAKE_COLOR,
                    borderRadius: 4,
                },
            ];
        }

        function buildChart() {
            const startIdx = (page - 1) * pageSize;
            const slice = sorted.slice(startIdx, startIdx + pageSize);
            if (wrapEl) {
                wrapEl.style.height = chartHeight(slice.length) + "px";
                wrapEl.style.minWidth = chartMinWidth(slice.length) + "px";
                wrapEl.classList.remove("hidden");
            }

            const labels = slice.map(function (q) {
                return questionLabel(q);
            });
            const isMistakes = metric === "mistakes";
            const config = {
                type: "bar",
                data: {
                    labels: labels,
                    datasets: isMistakes
                        ? mistakesDatasets(slice)
                        : confidenceDatasets(slice),
                },
                options: {
                    indexAxis: "x",
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            stacked: !isMistakes,
                            grid: { display: false },
                            title: {
                                display: true,
                                text: "Questions",
                            },
                        },
                        y: {
                            stacked: !isMistakes,
                            beginAtZero: true,
                            suggestedMax: isMistakes ? 100 : undefined,
                            ticks: isMistakes
                                ? {
                                      precision: 0,
                                      stepSize: 50,
                                      callback: function (value) {
                                          if (value === 0 || value === 50 || value === 100) {
                                              return value;
                                          }
                                          return "";
                                      },
                                  }
                                : { precision: 0 },
                            grid: { color: "#f1f5f9" },
                            title: {
                                display: true,
                                text: isMistakes
                                    ? "Number of mistakes"
                                    : "Confidence level (students)",
                            },
                        },
                    },
                    plugins: {
                        legend: {
                            position: "bottom",
                            align: "center",
                            display: !isMistakes,
                        },
                        tooltip: {
                            callbacks: {
                                title: function (items) {
                                    const idx = items[0] && items[0].dataIndex;
                                    const q = slice[idx];
                                    if (!q) return "";
                                    return (
                                        questionLabel(q) +
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

        function setMetric(nextMetric) {
            metric = nextMetric === "mistakes" ? "mistakes" : "confidence";
            sorted = sortedQuestions();
            totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
            page = 1;
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
        if (metricSelect) {
            metricSelect.addEventListener("change", function () {
                setMetric(metricSelect.value);
            });
        }

        return buildChart();
    }

    window.ExamiQUI = window.ExamiQUI || {};
    window.ExamiQUI.HEATMAP_TIER_COLORS = TIER_COLORS;
    window.ExamiQUI.sortHeatmapQuestions = sortByQuestionNumber;
    window.ExamiQUI.renderHeatmapPriorityChart = renderHeatmapPriorityChart;
})();
