/* Reassign dialog on the Faculty Courses assignment table.
 *
 * Each row's Reassign button opens that row's native <dialog>; the form
 * inside posts to the reassign endpoint. No-JS fallback: the standalone
 * reassign page still exists at the same URL.
 */
(function () {
    "use strict";

    function openDialog(dialog) {
        if (dialog && typeof dialog.showModal === "function") {
            dialog.showModal();
        }
    }

    function closeDialog(dialog) {
        if (dialog && typeof dialog.close === "function") {
            dialog.close();
        }
    }

    document.addEventListener("click", function (event) {
        var opener = event.target.closest("[data-reassign-open]");
        if (opener) {
            var kebab = opener.closest("details.account-kebab");
            if (kebab) kebab.removeAttribute("open");
            openDialog(document.getElementById(opener.getAttribute("data-reassign-open")));
            return;
        }
        var closer = event.target.closest("[data-close-reassign]");
        if (closer) {
            closeDialog(closer.closest("dialog"));
            return;
        }
        var dialogEl = event.target.closest("dialog.coord-dialog");
        if (dialogEl && event.target === dialogEl) {
            closeDialog(dialogEl);
        }
    });
})();
