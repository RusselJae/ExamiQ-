/**
 * Client-side search, type filters, sort, and month grouping for materials libraries.
 */
(function () {
    "use strict";

    function monthLabel(iso) {
        if (!iso) return "Unknown date";
        var d = new Date(iso);
        if (isNaN(d.getTime())) return "Unknown date";
        return d.toLocaleString(undefined, { month: "long", year: "numeric" });
    }

    function initLibrary(root) {
        var search = root.querySelector("[data-library-search]");
        var list = root.querySelector("[data-library-list]");
        var items = Array.prototype.slice.call(root.querySelectorAll("[data-library-item]"));
        var emptyFilter = root.querySelector("[data-library-empty-filter]");
        var countEl = root.querySelector("[data-library-count]");
        var chips = Array.prototype.slice.call(root.querySelectorAll("[data-library-filter]"));
        var sortSelect = root.querySelector("[data-library-sort]");
        var activeType = "";
        var activeExt = "";

        function clearGroups() {
            if (!list) return;
            Array.prototype.slice
                .call(list.querySelectorAll("[data-library-group]"))
                .forEach(function (group) {
                    group.remove();
                });
        }

        function rebuildGroups(orderedVisible) {
            if (!list) return;
            clearGroups();
            var mode = (sortSelect && sortSelect.value) || "newest";
            var useGroups = mode !== "title";
            var currentKey = null;
            var currentBody = null;

            orderedVisible.forEach(function (item) {
                if (!useGroups) {
                    list.appendChild(item);
                    return;
                }
                var key = item.getAttribute("data-month") || monthLabel(item.getAttribute("data-created"));
                if (key !== currentKey) {
                    currentKey = key;
                    var group = document.createElement("section");
                    group.className = "materials-library__group";
                    group.setAttribute("data-library-group", key);
                    var header = document.createElement("button");
                    header.type = "button";
                    header.className = "materials-library__group-header";
                    header.setAttribute("aria-expanded", "true");
                    header.innerHTML =
                        '<span class="materials-library__group-title">' +
                        key +
                        '</span><svg class="materials-library__group-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/></svg>';
                    currentBody = document.createElement("div");
                    currentBody.className = "materials-library__group-body";
                    header.addEventListener("click", function () {
                        var open = header.getAttribute("aria-expanded") !== "false";
                        header.setAttribute("aria-expanded", open ? "false" : "true");
                        currentBody.classList.toggle("is-collapsed", open);
                    });
                    group.appendChild(header);
                    group.appendChild(currentBody);
                    list.appendChild(group);
                }
                currentBody.appendChild(item);
            });
        }

        function sortItems() {
            var mode = (sortSelect && sortSelect.value) || "newest";
            return items.slice().sort(function (a, b) {
                if (mode === "title") {
                    return (a.getAttribute("data-title") || "").localeCompare(
                        b.getAttribute("data-title") || ""
                    );
                }
                var ta = a.getAttribute("data-created") || "";
                var tb = b.getAttribute("data-created") || "";
                if (mode === "oldest") return ta.localeCompare(tb);
                return tb.localeCompare(ta);
            });
        }

        function apply() {
            var q = ((search && search.value) || "").trim().toLowerCase();
            var ordered = sortItems();
            var visible = [];
            ordered.forEach(function (item) {
                var title = item.getAttribute("data-title") || "";
                var type = item.getAttribute("data-type") || "";
                var ext = (item.getAttribute("data-ext") || "").toUpperCase();
                var matchQ = !q || title.indexOf(q) !== -1;
                var matchT = !activeType || type === activeType;
                var matchE = !activeExt || ext === activeExt;
                var show = matchQ && matchT && matchE;
                item.classList.toggle("hidden", !show);
                if (show) visible.push(item);
            });
            rebuildGroups(visible.length ? visible : ordered.filter(function () { return false; }));
            // Keep hidden non-matches out of the DOM groups but retain references.
            ordered.forEach(function (item) {
                if (item.classList.contains("hidden") && item.parentNode) {
                    // Leave hidden items detached from visible groups; stash at end of list.
                    list.appendChild(item);
                }
            });
            if (emptyFilter) {
                emptyFilter.classList.toggle("hidden", visible.length > 0 || !items.length);
            }
            if (countEl) {
                countEl.textContent =
                    visible.length + (visible.length === 1 ? " item" : " items");
            }
        }

        chips.forEach(function (chip) {
            chip.addEventListener("click", function () {
                var ext = (chip.getAttribute("data-ext") || "").toUpperCase();
                if (ext) {
                    activeExt = ext;
                    activeType = "";
                } else {
                    activeExt = "";
                    activeType = chip.getAttribute("data-library-filter") || "";
                }
                chips.forEach(function (other) {
                    other.classList.toggle("is-active", other === chip);
                });
                apply();
            });
        });

        if (search) {
            try {
                var params = new URLSearchParams(window.location.search);
                var preset = params.get("q");
                if (preset && !search.value) search.value = preset;
            } catch (e) { /* ignore */ }
            search.addEventListener("input", apply);
        }
        if (sortSelect) {
            sortSelect.addEventListener("change", apply);
        }

        /* Toolbar chrome: Filter hides/shows the filter panel; Reset clears
           the search and the type filter, then re-applies. */
        var toolbarToggle = root.querySelector("[data-toolbar-toggle]");
        var toolbarPanel = root.querySelector("[data-toolbar-panel]");
        if (toolbarToggle && toolbarPanel && toolbarPanel.dataset.bound !== "1") {
            toolbarPanel.dataset.bound = "1";
            var desktop = window.matchMedia("(min-width: 640px)").matches;
            if (!desktop) {
                toolbarPanel.classList.add("hidden");
            }
            toolbarToggle.addEventListener("click", function () {
                var hidden = toolbarPanel.classList.toggle("hidden");
                toolbarToggle.setAttribute(
                    "aria-expanded",
                    hidden ? "false" : "true"
                );
            });
        }
        var toolbarReset = root.querySelector("[data-toolbar-reset]");
        if (toolbarReset && toolbarReset.dataset.bound !== "1") {
            toolbarReset.dataset.bound = "1";
            toolbarReset.addEventListener("click", function () {
                if (search) search.value = "";
                activeExt = "";
                activeType = "";
                chips.forEach(function (chip) {
                    var isAll = ((chip.getAttribute("data-ext") || "") === "")
                        && ((chip.getAttribute("data-library-filter") || "") === "");
                    chip.classList.toggle("is-active", isAll);
                });
                apply();
            });
        }
        apply();
    }

    function initFileName() {
        var input = document.getElementById("material-file");
        var label = document.querySelector("[data-file-name]");
        var nameInput = document.querySelector("[data-original-name]");
        if (!input) return;
        input.addEventListener("change", function () {
            var fileName = input.files && input.files[0] ? input.files[0].name : "";
            if (label) {
                label.textContent = fileName || "No file chosen";
            }
            if (nameInput && fileName) {
                if (!nameInput.value.trim() || nameInput.dataset.autoFilled === "1") {
                    nameInput.value = fileName;
                    nameInput.dataset.autoFilled = "1";
                }
            }
        });
        if (nameInput) {
            nameInput.addEventListener("input", function () {
                nameInput.dataset.autoFilled = "0";
            });
        }
    }

    function initDropzone() {
        var zone = document.querySelector("[data-dropzone]");
        var input = document.getElementById("material-file");
        var label = document.querySelector("[data-file-name]");
        var submit = document.querySelector("[data-upload-submit]");
        var defaultHint = "or browse from your device";
        if (!zone || !input) return;

        function refreshName() {
            var fileName = input.files && input.files[0] ? input.files[0].name : "";
            if (label) {
                label.textContent = fileName || defaultHint;
            }
            if (submit && !submit.disabled) {
                submit.disabled = !fileName && submit.hasAttribute("data-require-file");
            }
        }

        zone.addEventListener("click", function (event) {
            if (event.target.closest("button") || event.target.closest("a")) return;
            if (input.disabled) return;
            input.click();
        });
        ["dragenter", "dragover"].forEach(function (name) {
            zone.addEventListener(name, function (event) {
                event.preventDefault();
                if (input.disabled) return;
                zone.classList.add("is-dragover");
            });
        });
        ["dragleave", "drop"].forEach(function (name) {
            zone.addEventListener(name, function (event) {
                event.preventDefault();
                zone.classList.remove("is-dragover");
            });
        });
        zone.addEventListener("drop", function (event) {
            if (input.disabled) return;
            var files = event.dataTransfer && event.dataTransfer.files;
            if (files && files.length) {
                input.files = files;
                input.dispatchEvent(new Event("change", { bubbles: true }));
                refreshName();
            }
        });
        input.addEventListener("change", refreshName);
    }

    function init() {
        document.querySelectorAll("[data-materials-library]").forEach(initLibrary);
        initFileName();
        initDropzone();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
