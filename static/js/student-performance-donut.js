/**
 * Student dashboard donut: confidence × correctness categories.
 */
(function () {
    "use strict";

    var COLORS = ["#0F766E", "#F59E0B", "#1D4ED8", "#DC2626"];

    function renderLegend(el, slices, total) {
        if (!el) return;
        if (!slices || !slices.length || !total) {
            el.hidden = true;
            el.innerHTML = "";
            return;
        }
        el.hidden = false;
        el.innerHTML = slices
            .map(function (slice, index) {
                var color = COLORS[index % COLORS.length];
                return (
                    '<div class="student-donut-legend__item">' +
                    '<span class="student-donut-legend__swatch" style="background:' +
                    color +
                    '"></span>' +
                    '<span class="student-donut-legend__label">' +
                    slice.label +
                    "</span>" +
                    '<span class="student-donut-legend__value">' +
                    slice.value +
                    " (" +
                    slice.percent +
                    "%)</span>" +
                    "</div>"
                );
            })
            .join("");
    }

    function renderCenter(el, donut) {
        if (!el) return;
        var total = donut.total || 0;
        if (!total) {
            el.hidden = true;
            el.innerHTML = "";
            return;
        }
        el.hidden = false;
        var pct = donut.percent_correct;
        var primary =
            typeof pct === "number"
                ? pct.toString().replace(/\.0$/, "") + "%"
                : String(total);
        var secondary = typeof pct === "number" ? "correct" : "answers";
        if (typeof pct === "number") {
            secondary = "correct · " + total + " ans.";
        }
        el.innerHTML =
            '<span class="student-donut-center__value">' +
            primary +
            "</span>" +
            '<span class="student-donut-center__label">' +
            secondary +
            "</span>";
    }

    function renderInsight(el, donut) {
        if (!el) return;
        if (!donut.insight) {
            el.hidden = true;
            el.innerHTML = "";
            return;
        }
        el.hidden = false;
        var link = "";
        if (donut.insight_url) {
            link =
                ' <a class="student-confidence-card__insight-link" href="' +
                donut.insight_url +
                '">' +
                (donut.insight_link_label || "Review those questions") +
                "</a>";
        }
        el.innerHTML = donut.insight + link;
    }

    function renderScope(el, donut) {
        if (!el || !donut.scope_line) return;
        el.textContent = donut.scope_line;
    }

    function renderStudentPerformanceDonut(opts) {
        var canvas = document.getElementById(opts.canvasId || "studentTrendsChart");
        var emptyEl = document.getElementById(opts.emptyEl || "student-trends-empty");
        var wrapEl = document.getElementById(opts.wrapEl || "studentTrendsChartWrap");
        var legendEl = document.getElementById(opts.legendEl || "student-confidence-legend");
        var centerEl = document.getElementById(opts.centerEl || "student-donut-center");
        var insightEl = document.getElementById(
            opts.insightEl || "student-confidence-insight"
        );
        var scopeEl = document.getElementById(opts.scopeEl || "student-trends-scope");
        if (!canvas || typeof Chart === "undefined") return null;

        var donut = (opts.data && opts.data.donut) || { total: 0, slices: [] };
        var slices = (donut.slices || []).filter(function (s) {
            return s.value > 0;
        });
        var total = donut.total || 0;

        renderScope(scopeEl, donut);

        if (!total || !slices.length) {
            if (wrapEl) wrapEl.hidden = true;
            if (emptyEl) emptyEl.classList.remove("hidden");
            renderLegend(legendEl, [], 0);
            renderCenter(centerEl, { total: 0 });
            renderInsight(insightEl, {});
            return null;
        }
        if (wrapEl) wrapEl.hidden = false;
        if (emptyEl) emptyEl.classList.add("hidden");

        var chart = new Chart(canvas.getContext("2d"), {
            type: "doughnut",
            data: {
                labels: slices.map(function (s) {
                    return s.label;
                }),
                datasets: [
                    {
                        data: slices.map(function (s) {
                            return s.value;
                        }),
                        backgroundColor: slices.map(function (_s, i) {
                            return COLORS[i % COLORS.length];
                        }),
                        borderWidth: 2,
                        borderColor: "#ffffff",
                        hoverOffset: 6,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "62%",
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function (ctx) {
                                var slice = slices[ctx.dataIndex] || {};
                                return (
                                    (slice.label || ctx.label) +
                                    ": " +
                                    (slice.value || 0) +
                                    " (" +
                                    (slice.percent || 0) +
                                    "%)"
                                );
                            },
                        },
                    },
                },
            },
        });
        renderLegend(legendEl, slices, total);
        renderCenter(centerEl, donut);
        renderInsight(insightEl, donut);
        return chart;
    }

    window.ExamiQUI = window.ExamiQUI || {};
    window.ExamiQUI.renderStudentPerformanceDonut = renderStudentPerformanceDonut;

    /**
     * Faculty student-detail pages reuse this donut. They already ship
     * `summary.dashboard_trends` as #student-detail-trends-data, so the same
     * payload (including its `donut` key) drives the chart — no inline config.
     */
    function autoRenderStudentDetailDonut() {
        var dataEl = document.getElementById("student-detail-trends-data");
        if (!dataEl || !document.getElementById("studentDetailDonut")) return;
        renderStudentPerformanceDonut({
            canvasId: "studentDetailDonut",
            wrapEl: "studentDetailDonutWrap",
            emptyEl: "student-detail-donut-empty",
            legendEl: "student-detail-donut-legend",
            centerEl: "student-detail-donut-center",
            insightEl: "student-detail-donut-insight",
            scopeEl: "student-detail-donut-scope",
            data: JSON.parse(dataEl.textContent),
        });
    }

    document.addEventListener("DOMContentLoaded", autoRenderStudentDetailDonut);

    /**
     * Professor overview: same renderer, payload in #overview-donut-data.
     */
    function autoRenderOverviewDonut() {
        var dataEl = document.getElementById("overview-donut-data");
        if (!dataEl || !document.getElementById("overviewDonutChart")) return;
        renderStudentPerformanceDonut({
            canvasId: "overviewDonutChart",
            wrapEl: "overviewDonutWrap",
            emptyEl: "overview-donut-empty",
            legendEl: "overview-donut-legend",
            centerEl: "overview-donut-center",
            insightEl: "overview-donut-insight",
            scopeEl: "overview-donut-scope",
            data: { donut: JSON.parse(dataEl.textContent) },
        });
    }

    document.addEventListener("DOMContentLoaded", autoRenderOverviewDonut);
})();
