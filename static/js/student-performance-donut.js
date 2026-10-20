/**
 * Student dashboard donut: confidence × correctness categories.
 */
(function () {
    "use strict";

    var COLORS = ["#0F766E", "#F59E0B", "#1D4ED8", "#DC2626"];

    var STATUS_LABELS = {
        overconfident: "Overconfident",
        underconfident: "Underconfident",
        confident: "Confident",
    };

    function escapeHtml(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    /**
     * Legend footer: the plain-language insight plus the calibration status
     * (bolded, with a button that opens the full computation).
     */
    function renderLegendFooter(donut) {
        if (!donut) return "";
        var insight = donut.insight || "";
        var status = donut.calibration_status || "";
        if (!insight && !status) return "";

        var html = "";
        if (insight) {
            var link = "";
            if (donut.insight_url) {
                link =
                    ' <a class="student-confidence-card__insight-link" href="' +
                    donut.insight_url +
                    '">' +
                    (donut.insight_link_label || "Review those questions") +
                    "</a>";
            }
            html +=
                '<p class="student-donut-legend__insight">' +
                escapeHtml(insight) +
                link +
                "</p>";
        }
        if (status) {
            html +=
                '<p class="student-donut-legend__status">' +
                '<button type="button" class="student-donut-legend__status-label" data-status="' +
                escapeHtml(status) +
                '" data-calibration-open aria-haspopup="dialog">' +
                escapeHtml(STATUS_LABELS[status] || status) +
                "</button></p>";
        }
        return html;
    }

    function renderLegend(el, slices, total, donut) {
        if (!el) return;
        el.__examiqDonut = donut || null;
        if (!slices || !slices.length || !total) {
            el.hidden = true;
            el.innerHTML = "";
            return;
        }
        el.hidden = false;
        var items = slices
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
        el.innerHTML = items + renderLegendFooter(donut);
    }

    /* ------------------------------------------------------------------ *
     * Calibration modal: the 4 × 3 breakdown behind the status badge.
     * ------------------------------------------------------------------ */
    var MODAL_ID = "calibration-modal";
    var lastFocused = null;

    function calibrationModal() {
        var el = document.getElementById(MODAL_ID);
        if (el) return el;
        el = document.createElement("div");
        el.id = MODAL_ID;
        el.className = "calibration-modal-root hidden";
        el.setAttribute("role", "dialog");
        el.setAttribute("aria-modal", "true");
        el.setAttribute("aria-labelledby", "calibration-modal-title");
        el.innerHTML =
            '<div class="calibration-modal-overlay" data-calibration-close></div>' +
            '<div class="calibration-modal-card">' +
            '<button type="button" class="calibration-modal-close" data-calibration-close aria-label="Close">&times;</button>' +
            '<p class="calibration-modal-eyebrow">Confidence calibration</p>' +
            '<h2 class="calibration-modal-title" id="calibration-modal-title"></h2>' +
            '<p class="calibration-modal-lead" data-calibration-lead></p>' +
            '<div class="calibration-modal-grid" data-calibration-grid></div>' +
            '<ul class="calibration-modal-calc" data-calibration-calc></ul>' +
            '<p class="calibration-modal-rule" data-calibration-rule></p>' +
            "</div>";
        document.body.appendChild(el);
        el.addEventListener("click", function (event) {
            if (event.target.closest("[data-calibration-close]")) {
                closeCalibrationModal();
            }
        });
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") closeCalibrationModal();
        });
        return el;
    }

    function closeCalibrationModal() {
        var el = document.getElementById(MODAL_ID);
        if (!el) return;
        el.classList.add("hidden");
        if (lastFocused && lastFocused.focus) lastFocused.focus();
        lastFocused = null;
    }

    function metricLine(metric, isDriver) {
        if (!metric) return "";
        return (
            '<li class="calibration-modal-calc__item' +
            (isDriver ? " is-driver" : "") +
            '">' +
            "<strong>" +
            metric.value +
            "</strong> of <strong>" +
            metric.total +
            "</strong> " +
            escapeHtml(metric.sentence || metric.label) +
            ' &rarr; <strong>' +
            metric.percent +
            "%</strong></li>"
        );
    }

    function openCalibrationModal(donut) {
        if (!donut) return;
        var cal = donut.calibration || {};
        var status = cal.status || donut.calibration_status || "";
        var slices = donut.slices || [];
        var metrics = cal.metrics || [];
        var modal = calibrationModal();

        modal.querySelector("#calibration-modal-title").textContent =
            "Why this is " + (cal.label || STATUS_LABELS[status] || status);
        modal.querySelector("[data-calibration-lead]").textContent =
            cal.summary || "How confidence lines up with correctness.";

        // 4 columns (one per category) × 3 rows (name, count, share).
        var grid = "";
        slices.forEach(function (slice, index) {
            grid +=
                '<div class="calibration-modal-cell calibration-modal-cell--head">' +
                '<span class="calibration-modal-dot" style="background:' +
                COLORS[index % COLORS.length] +
                '"></span>' +
                escapeHtml(slice.label) +
                "</div>";
        });
        slices.forEach(function (slice) {
            grid +=
                '<div class="calibration-modal-cell calibration-modal-cell--value' +
                (slice.value ? "" : " is-empty") +
                '">' +
                slice.value +
                "</div>";
        });
        slices.forEach(function (slice) {
            grid +=
                '<div class="calibration-modal-cell calibration-modal-cell--percent' +
                (slice.value ? "" : " is-empty") +
                '">' +
                slice.percent +
                "%</div>";
        });
        modal.querySelector("[data-calibration-grid]").innerHTML = grid;

        modal.querySelector("[data-calibration-calc]").innerHTML =
            metricLine(metrics[0], cal.driver === "sure_incorrect") +
            metricLine(metrics[1], cal.driver === "guessing_correct");
        modal.querySelector("[data-calibration-rule]").textContent =
            cal.rule || "";

        lastFocused = document.activeElement;
        modal.classList.remove("hidden");
        var close = modal.querySelector(".calibration-modal-close");
        if (close) close.focus();
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

        // Keep the options so the range/section filters can re-render in place.
        canvas.__examiqDonutOptions = opts;

        var donut = (opts.data && opts.data.donut) || { total: 0, slices: [] };
        var slices = (donut.slices || []).filter(function (s) {
            return s.value > 0;
        });
        var total = donut.total || 0;

        renderScope(scopeEl, donut);

        if (!total || !slices.length) {
            if (wrapEl) wrapEl.hidden = true;
            if (emptyEl) emptyEl.classList.remove("hidden");
            renderLegend(legendEl, [], 0, donut);
            renderCenter(centerEl, { total: 0 });
            renderInsight(insightEl, {});
            return null;
        }
        if (wrapEl) wrapEl.hidden = false;
        if (emptyEl) emptyEl.classList.add("hidden");

        // Re-rendering the same canvas needs the old chart released first.
        var existing = Chart.getChart(canvas);
        if (existing) existing.destroy();

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
        renderLegend(legendEl, slices, total, donut);
        renderCenter(centerEl, donut);
        renderInsight(insightEl, donut);
        return chart;
    }

    window.ExamiQUI = window.ExamiQUI || {};
    window.ExamiQUI.renderStudentPerformanceDonut = renderStudentPerformanceDonut;
    window.ExamiQUI.openCalibrationModal = openCalibrationModal;

    /* The status badge opens the computation modal. */
    document.addEventListener("click", function (event) {
        var trigger = event.target.closest("[data-calibration-open]");
        if (!trigger) return;
        var legend = trigger.closest(".student-donut-legend");
        var donut = legend && legend.__examiqDonut;
        if (!donut) return;
        event.preventDefault();
        openCalibrationModal(donut);
    });

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
