(function () {
    "use strict";

    function getCsrfToken() {
        const input = document.querySelector("[name=csrfmiddlewaretoken]");
        if (input) return input.value;
        const match = document.cookie.match(/csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    function bindGenerateButtons(root) {
        (root || document).querySelectorAll(".feedback-generate-btn").forEach(function (btn) {
            if (btn.dataset.bound) return;
            btn.dataset.bound = "1";

            btn.addEventListener("click", function () {
                const url = btn.dataset.generateFeedbackUrl;
                const answerId = btn.dataset.answerId;
                const card = document.getElementById("answer-review-" + answerId);
                if (!url || !card || btn.disabled) return;

                const originalText = btn.textContent;
                btn.disabled = true;
                btn.textContent = "Generating…";

                fetch(url, {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": getCsrfToken(),
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    credentials: "same-origin",
                })
                    .then(function (resp) {
                        if (!resp.ok) throw new Error("generate failed");
                        return resp.text();
                    })
                    .then(function (html) {
                        card.outerHTML = html;
                        bindGenerateButtons(document);
                    })
                    .catch(function () {
                        btn.disabled = false;
                        btn.textContent = originalText;
                        if (typeof showToast === "function") {
                            showToast("Could not generate feedback. Please try again.", "error");
                        }
                    });
            });
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        bindGenerateButtons(document);
    });
})();
