/**
 * Material document screen: header actions and the save-state indicator.
 *
 * The overflow menu itself is driven by the shared `[data-dropdown]` helper in
 * examiq-ui.js, so this file only handles rename / move-to-course and the
 * "All changes saved" state.
 *
 * The embedded editor reports its own state by dispatching a
 * `materials:savestate` event on `document` (see materials-office.js), so the
 * indicator reflects real unsaved changes rather than just the metadata form.
 */
(function () {
    "use strict";

    function ready(fn) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", fn);
        } else {
            fn();
        }
    }

    var LABELS = {
        saved: "All changes saved",
        dirty: "Unsaved changes",
        saving: "Saving…",
    };

    function setSaveStatus(state) {
        var el = document.querySelector("[data-save-status]");
        if (!el) return;
        var text = LABELS[state] || LABELS.saved;
        el.setAttribute("data-state", state);
        var label = el.querySelector("[data-save-status-text]");
        if (label) label.textContent = text;
    }

    function initRenameRow() {
        var row = document.querySelector("[data-doc-rename-row]");
        var trigger = document.querySelector("[data-doc-rename]");
        if (!row || !trigger) return;
        trigger.addEventListener("click", function () {
            row.classList.toggle("hidden");
            if (!row.classList.contains("hidden")) {
                var input = row.querySelector("input");
                if (input) {
                    input.focus();
                    input.select();
                }
            }
        });
    }

    function initMoveToCourse() {
        var trigger = document.querySelector("[data-doc-move-course]");
        var select = document.querySelector("[data-doc-course]");
        if (!trigger || !select) return;
        trigger.addEventListener("click", function () {
            select.classList.add("is-highlighted");
            select.focus();
            window.setTimeout(function () {
                select.classList.remove("is-highlighted");
            }, 2000);
        });
    }

    function initFormState() {
        var form = document.querySelector("[data-doc-form]");
        if (!form) return;
        form.addEventListener("submit", function () {
            setSaveStatus("saving");
        });
    }

    function initEditorState() {
        document.addEventListener("materials:savestate", function (event) {
            var detail = event.detail || {};
            if (detail.state) setSaveStatus(detail.state);
        });
    }

    ready(function () {
        initRenameRow();
        initMoveToCourse();
        initFormState();
        initEditorState();
    });

    /* Exposed so the editor can push state without a custom-event round trip. */
    window.ExamiQMaterials = window.ExamiQMaterials || {};
    window.ExamiQMaterials.setSaveStatus = setSaveStatus;
})();