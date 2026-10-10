(function () {
    "use strict";

    var card = document.querySelector("[data-confidence-card]");
    if (!card) return;

    var toggle = card.querySelector("[data-confidence-info-toggle]");
    var popover = card.querySelector("[data-confidence-info]");
    if (!toggle || !popover) return;

    function close() {
        popover.setAttribute("hidden", "");
        toggle.setAttribute("aria-expanded", "false");
    }

    toggle.addEventListener("click", function (event) {
        event.stopPropagation();
        var open = popover.hasAttribute("hidden");
        if (open) {
            popover.removeAttribute("hidden");
            toggle.setAttribute("aria-expanded", "true");
        } else {
            close();
        }
    });

    document.addEventListener("click", function (event) {
        if (!card.contains(event.target)) {
            close();
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") close();
    });
})();
