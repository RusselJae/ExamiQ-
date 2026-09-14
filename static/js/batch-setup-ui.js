/**
 * Batch setup UI: pill toggles, source tabs, count stepper, dropzone.
 */
(function () {
    "use strict";

    function initPills(root) {
        (root || document).querySelectorAll("[data-pill-group]").forEach(function (group) {
            if (group.dataset.bound === "1") return;
            group.dataset.bound = "1";
            var targetId = group.getAttribute("data-pill-target");
            var select = targetId ? document.getElementById(targetId) : null;
            group.querySelectorAll("[data-pill-value]").forEach(function (btn) {
                btn.addEventListener("click", function () {
                    var value = btn.getAttribute("data-pill-value") || "";
                    group.querySelectorAll("[data-pill-value]").forEach(function (other) {
                        var on = other === btn;
                        other.classList.toggle("is-selected", on);
                        other.setAttribute("aria-pressed", on ? "true" : "false");
                    });
                    if (select) {
                        select.value = value;
                        select.dispatchEvent(new Event("change", { bubbles: true }));
                    }
                });
            });
        });
    }

    function initSourceTabs(root) {
        (root || document).querySelectorAll("[data-source-tabs]").forEach(function (wrap) {
            if (wrap.dataset.bound === "1") return;
            wrap.dataset.bound = "1";
            var tabs = wrap.querySelectorAll("[data-source-tab]");
            var panels = wrap.querySelectorAll("[data-source-panel]");
            var library = document.getElementById("ai-library-document");
            var fileInput = document.getElementById("ai-source-file");
            var filenameEl = wrap.querySelector("[data-dropzone-filename]");

            function showTab(name) {
                tabs.forEach(function (tab) {
                    var on = tab.getAttribute("data-source-tab") === name;
                    tab.classList.toggle("is-selected", on);
                    tab.setAttribute("aria-selected", on ? "true" : "false");
                });
                panels.forEach(function (panel) {
                    var on = panel.getAttribute("data-source-panel") === name;
                    panel.classList.toggle("hidden", !on);
                    if (on) panel.removeAttribute("hidden");
                    else panel.setAttribute("hidden", "");
                });
                if (name === "saved" && fileInput) {
                    fileInput.value = "";
                    if (filenameEl) {
                        filenameEl.textContent = "";
                        filenameEl.classList.add("hidden");
                    }
                }
                if (name === "upload" && library) {
                    library.value = "";
                }
            }

            tabs.forEach(function (tab) {
                tab.addEventListener("click", function () {
                    showTab(tab.getAttribute("data-source-tab") || "saved");
                });
            });
        });
    }

    function initSteppers(root) {
        (root || document).querySelectorAll("[data-stepper]").forEach(function (stepper) {
            if (stepper.dataset.bound === "1") return;
            stepper.dataset.bound = "1";
            var input = stepper.querySelector("input[type='number']");
            var min = parseInt(stepper.getAttribute("data-stepper-min") || "1", 10);
            var max = parseInt(stepper.getAttribute("data-stepper-max") || "50", 10);
            if (!input) return;

            function clamp(n) {
                if (isNaN(n)) n = min;
                return Math.max(min, Math.min(max, n));
            }

            function setValue(n) {
                input.value = String(clamp(n));
                input.dispatchEvent(new Event("change", { bubbles: true }));
            }

            var dec = stepper.querySelector("[data-stepper-dec]");
            var inc = stepper.querySelector("[data-stepper-inc]");
            if (dec) {
                dec.addEventListener("click", function () {
                    setValue(parseInt(input.value, 10) - 1);
                });
            }
            if (inc) {
                inc.addEventListener("click", function () {
                    setValue(parseInt(input.value, 10) + 1);
                });
            }
            input.addEventListener("change", function () {
                setValue(parseInt(input.value, 10));
            });
        });
    }

    function initDropzones(root) {
        (root || document).querySelectorAll("[data-dropzone]").forEach(function (zone) {
            if (zone.dataset.bound === "1") return;
            zone.dataset.bound = "1";
            var input = zone.querySelector('input[type="file"]');
            var chooseBtn = zone.querySelector("[data-dropzone-choose]");
            var filenameEl = zone.querySelector("[data-dropzone-filename]");
            if (!input) return;

            function showName() {
                var file = input.files && input.files[0];
                if (!filenameEl) return;
                if (file) {
                    filenameEl.textContent = file.name;
                    filenameEl.classList.remove("hidden");
                } else {
                    filenameEl.textContent = "";
                    filenameEl.classList.add("hidden");
                }
            }

            if (chooseBtn) {
                chooseBtn.addEventListener("click", function (e) {
                    e.preventDefault();
                    input.click();
                });
            }
            zone.addEventListener("click", function (e) {
                if (e.target.closest("[data-dropzone-choose]")) return;
                if (e.target === input) return;
                input.click();
            });
            input.addEventListener("change", showName);

            ["dragenter", "dragover"].forEach(function (evt) {
                zone.addEventListener(evt, function (e) {
                    e.preventDefault();
                    e.stopPropagation();
                    zone.classList.add("is-dragover");
                });
            });
            ["dragleave", "drop"].forEach(function (evt) {
                zone.addEventListener(evt, function (e) {
                    e.preventDefault();
                    e.stopPropagation();
                    zone.classList.remove("is-dragover");
                });
            });
            zone.addEventListener("drop", function (e) {
                var files = e.dataTransfer && e.dataTransfer.files;
                if (!files || !files.length) return;
                try {
                    var dt = new DataTransfer();
                    dt.items.add(files[0]);
                    input.files = dt.files;
                } catch (err) {
                    return;
                }
                showName();
                input.dispatchEvent(new Event("change", { bubbles: true }));
            });
        });
    }

    function init(root) {
        initPills(root);
        initSourceTabs(root);
        initSteppers(root);
        initDropzones(root);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            init(document);
        });
    } else {
        init(document);
    }
})();
