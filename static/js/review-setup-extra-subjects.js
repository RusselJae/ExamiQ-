/**
 * Toggle optional "Add other subjects" panel on Start Exam setup.
 */
(function () {
    "use strict";

    function init() {
        var btn = document.getElementById("toggle-extra-subjects-btn");
        var panel = document.getElementById("extra-subjects-panel");
        if (!btn || !panel) return;

        function isOpen() {
            return !panel.hasAttribute("hidden") && !panel.classList.contains("hidden");
        }

        function setOpen(open) {
            if (open) {
                panel.removeAttribute("hidden");
                panel.classList.remove("hidden");
                btn.setAttribute("aria-expanded", "true");
                btn.textContent = "Hide other subjects";
            } else {
                panel.setAttribute("hidden", "");
                panel.classList.add("hidden");
                btn.setAttribute("aria-expanded", "false");
                btn.textContent = "Add other subjects";
            }
        }

        setOpen(isOpen());
        btn.addEventListener("click", function () {
            setOpen(!isOpen());
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
