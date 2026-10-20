/**
 * Donut range / section filters.
 *
 * The pills are real links, so the page still works without JavaScript. When
 * JavaScript is available the click is intercepted: the fresh donut payload is
 * fetched and only the chart, legend and scope line are re-rendered — the
 * page itself never reloads.
 */
(function () {
    "use strict";

    function selectedParams(filters) {
        const params = {};
        filters.querySelectorAll("[data-donut-param]").forEach(function (group) {
            const name = group.getAttribute("data-donut-param");
            const active = group.querySelector(".overview-pill.is-selected");
            params[name] = active ? active.getAttribute("data-donut-value") || "" : "";
        });
        return params;
    }

    function applyValue(group, value) {
        group.querySelectorAll(".overview-pill").forEach(function (pill) {
            const on = (pill.getAttribute("data-donut-value") || "") === value;
            pill.classList.toggle("is-selected", on);
            pill.setAttribute("aria-pressed", on ? "true" : "false");
        });
    }

    function syncPills(filters, params) {
        filters.querySelectorAll("[data-donut-param]").forEach(function (group) {
            const name = group.getAttribute("data-donut-param");
            const value = params[name] === undefined ? "" : params[name];
            applyValue(group, value);
        });
    }

    function dataUrl(filters, params) {
        const base = filters.getAttribute("data-donut-data-url");
        if (!base) return "";
        const url = new URL(base, window.location.origin);
        Object.keys(params).forEach(function (key) {
            if (params[key]) url.searchParams.set(key, params[key]);
        });
        return url.toString();
    }

    /* Same page, with the chosen filters applied — the fallback when the
     * chart cannot be updated in place. */
    function pageUrl(params) {
        const url = new URL(window.location.href);
        Object.keys(params).forEach(function (key) {
            if (params[key]) url.searchParams.set(key, params[key]);
            else url.searchParams.delete(key);
        });
        return url.toString();
    }

    function pushUrl(params) {
        const url = new URL(window.location.href);
        Object.keys(params).forEach(function (key) {
            if (params[key]) url.searchParams.set(key, params[key]);
            else url.searchParams.delete(key);
        });
        window.history.pushState({ donut: true }, "", url.toString());
    }

    function render(canvas, donut) {
        const opts = canvas && canvas.__examiqDonutOptions;
        if (!opts || !window.ExamiQUI || !window.ExamiQUI.renderStudentPerformanceDonut) {
            return false;
        }
        const data = Object.assign({}, opts.data || {}, { donut: donut });
        window.ExamiQUI.renderStudentPerformanceDonut(Object.assign({}, opts, { data: data }));
        return true;
    }

    function load(filters, params) {
        const canvasId = filters.getAttribute("data-donut-canvas");
        const canvas = canvasId ? document.getElementById(canvasId) : null;
        const url = dataUrl(filters, params);
        if (!canvas || !url) {
            window.location.href = pageUrl(params);
            return;
        }
        filters.setAttribute("aria-busy", "true");
        fetch(url, {
            headers: { Accept: "application/json" },
            credentials: "same-origin",
        })
            .then(function (response) {
                if (!response.ok) throw new Error("Request failed");
                return response.json();
            })
            .then(function (payload) {
                const donut = (payload && payload.donut) || payload;
                if (!render(canvas, donut)) {
                    window.location.href = pageUrl(params);
                    return;
                }
                pushUrl(params);
            })
            .catch(function () {
                window.location.href = pageUrl(params);
            })
            .then(function () {
                filters.removeAttribute("aria-busy");
            });
    }

    function init(filters) {
        if (!filters || filters.dataset.bound === "1") return;
        filters.dataset.bound = "1";

        filters.addEventListener("click", function (event) {
            const pill = event.target.closest(".overview-pill[data-donut-value]");
            if (!pill || !filters.contains(pill)) return;
            event.preventDefault();
            if (pill.classList.contains("is-selected")) return;
            const group = pill.closest("[data-donut-param]");
            if (!group) return;
            applyValue(group, pill.getAttribute("data-donut-value") || "");
            const params = selectedParams(filters);
            load(filters, params);
        });
    }

    function initAll(scope) {
        (scope || document)
            .querySelectorAll("[data-donut-filters]")
            .forEach(init);
    }

    /* Keep the chart in sync with the address bar (browser back/forward). */
    window.addEventListener("popstate", function () {
        document.querySelectorAll("[data-donut-filters]").forEach(function (filters) {
            const params = selectedParams(filters);
            const url = new URL(window.location.href);
            filters.querySelectorAll("[data-donut-param]").forEach(function (group) {
                const name = group.getAttribute("data-donut-param");
                params[name] = url.searchParams.get(name) || "";
            });
            syncPills(filters, params);
            load(filters, params);
        });
    });

    window.ExamiQDonutFilters = { init: initAll };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            initAll();
        });
    } else {
        initAll();
    }
})();
