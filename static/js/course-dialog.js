/**
 * Native dialogs for the coordinator Add/Edit course forms.
 * The add dialog reopens automatically when the server re-renders with
 * form errors. Edit buttons carry the row's values in data attributes;
 * the shared edit dialog is populated from them and posts to the row's
 * edit URL (the standalone edit page remains as a fallback).
 */
(function () {
    "use strict";

    function bindOpenButtons(dialog, selector) {
        document.querySelectorAll(selector).forEach(function (btn) {
            if (btn.dataset.bound) return;
            btn.dataset.bound = "1";
            btn.addEventListener("click", function () {
                dialog.showModal();
            });
        });
    }

    function bindCloseButtons(dialog, selector) {
        dialog.querySelectorAll(selector).forEach(function (btn) {
            if (btn.dataset.bound) return;
            btn.dataset.bound = "1";
            btn.addEventListener("click", function () {
                dialog.close();
            });
        });
    }

    function closeParentKebab(btn) {
        var kebab = btn.closest("details.account-kebab");
        if (kebab) kebab.removeAttribute("open");
    }

    function bindEditDialog(dialog) {
        var form = dialog.querySelector("[data-edit-course-form]");
        if (!form) return;
        document.querySelectorAll("[data-edit-course]").forEach(function (btn) {
            if (btn.dataset.bound) return;
            btn.dataset.bound = "1";
            btn.addEventListener("click", function () {
                closeParentKebab(btn);
                form.action = btn.dataset.editUrl || "";
                var code = dialog.querySelector("[data-edit-field='code']");
                var name = dialog.querySelector("[data-edit-field='name']");
                var yearLevel = dialog.querySelector("[data-edit-field='year_level']");
                var semester = dialog.querySelector("[data-edit-field='semester']");
                if (code) code.value = btn.dataset.code || "";
                if (name) name.value = btn.dataset.name || "";
                if (yearLevel) yearLevel.value = btn.dataset.yearLevel || "";
                if (semester) semester.value = btn.dataset.semester || "";
                dialog.showModal();
            });
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (typeof HTMLDialogElement === "undefined") return;

        var addDialog = document.getElementById("add-course-dialog");
        if (addDialog && typeof addDialog.showModal === "function") {
            bindOpenButtons(addDialog, "[data-open-course-dialog]");
            bindCloseButtons(addDialog, "[data-close-course-dialog]");
            if (addDialog.dataset.hasErrors === "1") {
                addDialog.showModal();
            }
        }

        var rosterDialog = document.getElementById("add-roster-dialog");
        if (rosterDialog && typeof rosterDialog.showModal === "function") {
            bindOpenButtons(rosterDialog, "[data-open-roster-dialog]");
            bindCloseButtons(rosterDialog, "[data-close-roster-dialog]");
        }

        var editDialog = document.getElementById("edit-course-dialog");
        if (editDialog && typeof editDialog.showModal === "function") {
            bindCloseButtons(editDialog, "[data-close-course-dialog]");
            bindEditDialog(editDialog);
        }
    });
})();
