/**
 * Mark horizontally scrollable table wrappers so they receive a persistent,
 * sidebar-style horizontal scrollbar.
 */
(function () {
    "use strict";

    var WRAPPER_SELECTOR = [
        ".data-table-wrap",
        ".session-history-table-wrap",
        ".questions-table-wrap",
        ".masterlist-card",
        ".table-scroll",
        "[class*='overflow-x-auto']",
    ].join(",");

    function overflowX(el) {
        return window.getComputedStyle(el).overflowX;
    }

    function findWrapper(table) {
        var node = table.parentElement;
        for (var depth = 0; node && depth < 4; depth += 1) {
            if (
                node.matches(WRAPPER_SELECTOR) ||
                overflowX(node) === "auto" ||
                overflowX(node) === "scroll"
            ) {
                return node;
            }
            node = node.parentElement;
        }
        return table.parentElement;
    }

    function sync() {
        document.querySelectorAll("table").forEach(function (table) {
            var wrapper = findWrapper(table);
            if (!wrapper || wrapper.tagName === "BODY") return;
            wrapper.classList.add("table-scroll-indicator");
            var scrollable =
                (overflowX(wrapper) === "auto" || overflowX(wrapper) === "scroll") &&
                wrapper.scrollWidth > wrapper.clientWidth + 2;
            wrapper.classList.toggle("is-scrollable-x", scrollable);
        });
    }

    var pending = false;
    function schedule() {
        if (pending) return;
        pending = true;
        window.requestAnimationFrame(function () {
            pending = false;
            sync();
        });
    }

    document.addEventListener("DOMContentLoaded", schedule);
    document.addEventListener("htmx:afterSwap", schedule);
    window.addEventListener("resize", schedule);
    window.addEventListener("load", schedule);
    if (window.MutationObserver) {
        new MutationObserver(schedule).observe(document.documentElement, {
            childList: true,
            subtree: true,
        });
    }
})();
