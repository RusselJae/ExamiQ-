/**
 * Tabbed question editor (Details / Answers / Explanation / Steps).
 * Keeps panels mounted so form fields still submit when inactive.
 */
(function () {
  "use strict";

  function activateTab(root, target) {
    if (!target) return;
    root.querySelectorAll("[data-tab-target]").forEach(function (tab) {
      const active = tab.getAttribute("data-tab-target") === target;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    root.querySelectorAll("[data-tab-panel]").forEach(function (panel) {
      const active = panel.getAttribute("data-tab-panel") === target;
      panel.classList.toggle("is-active", active);
      panel.classList.toggle("hidden", !active);
      if (active) {
        panel.removeAttribute("hidden");
      } else {
        panel.setAttribute("hidden", "hidden");
      }
    });
  }

  function panelHasErrors(panel) {
    return !!(
      panel.querySelector(".errorlist, .text-red-600, .is-invalid, [aria-invalid='true']") ||
      (panel.querySelectorAll(".errorlist li").length > 0)
    );
  }

  function initRoot(root) {
    if (root.getAttribute("data-tabs-ready") === "1") return;
    root.setAttribute("data-tabs-ready", "1");

    root.addEventListener("click", function (event) {
      const tab = event.target.closest("[data-tab-target]");
      if (!tab || !root.contains(tab)) return;
      event.preventDefault();
      activateTab(root, tab.getAttribute("data-tab-target"));
    });

    // Open the first tab that contains validation errors.
    const panels = Array.prototype.slice.call(root.querySelectorAll("[data-tab-panel]"));
    const errored = panels.find(panelHasErrors);
    if (errored) {
      activateTab(root, errored.getAttribute("data-tab-panel"));
    } else {
      const initial =
        (root.querySelector(".question-edit-tab.is-active") ||
          root.querySelector("[data-tab-target]")) &&
        (
          root.querySelector(".question-edit-tab.is-active") ||
          root.querySelector("[data-tab-target]")
        ).getAttribute("data-tab-target");
      activateTab(root, initial || "details");
    }
  }

  function boot() {
    document.querySelectorAll("[data-question-edit-tabs]").forEach(initRoot);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
