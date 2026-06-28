(function () {
    "use strict";

    document.querySelectorAll(".landing-nav__link[href*='#']").forEach(function (link) {
        link.addEventListener("click", function (e) {
            const hash = link.getAttribute("href").split("#")[1];
            if (!hash) return;
            const target = document.getElementById(hash);
            if (target) {
                e.preventDefault();
                target.scrollIntoView({ behavior: "smooth", block: "start" });
            }
        });
    });
})();
