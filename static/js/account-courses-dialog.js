/* All-courses dialog on the chairperson User Accounts table.
 *
 * Each row with more than four courses renders a "+N" overflow chip that
 * opens that row's native <dialog> listing every course as pills. The chip
 * keeps its full-list `title` tooltip as a no-JS fallback.
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
        var opener = event.target.closest("[data-courses-open]");
        if (opener) {
            openDialog(document.getElementById(opener.getAttribute("data-courses-open")));
            return;
        }
        var closer = event.target.closest("[data-close-courses]");
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
