/**
 * Auth form helpers — password visibility toggle and strength checklist.
 */
(function () {
    "use strict";

    function initPasswordToggles(root) {
        root.querySelectorAll("[data-password-field]").forEach(function (wrap) {
            const input = wrap.querySelector("input");
            const toggle = wrap.querySelector("[data-password-toggle]");
            if (!input || !toggle) {
                return;
            }

            const showIcon = toggle.querySelector(".auth-password-toggle__icon--show");
            const hideIcon = toggle.querySelector(".auth-password-toggle__icon--hide");

            toggle.addEventListener("click", function () {
                const isHidden = input.type === "password";
                input.type = isHidden ? "text" : "password";
                toggle.setAttribute("aria-pressed", isHidden ? "true" : "false");
                toggle.setAttribute("aria-label", isHidden ? "Hide password" : "Show password");
                if (showIcon) {
                    showIcon.classList.toggle("hidden", isHidden);
                }
                if (hideIcon) {
                    hideIcon.classList.toggle("hidden", !isHidden);
                }
            });
        });
    }

    function evaluatePassword(value) {
        const hasLength = value.length >= 8;
        const notNumeric = value.length > 0 && !/^\d+$/.test(value);
        const mixed = /[A-Za-z]/.test(value) && /\d/.test(value);
        const special = /[A-Z]/.test(value) || /[^A-Za-z0-9]/.test(value);

        return {
            length: hasLength,
            "not-numeric": notNumeric,
            mixed: mixed,
            special: special,
        };
    }

    function initPasswordStrength(root) {
        const strengthPanel = root.querySelector("[data-password-strength]");
        const passwordInput = root.querySelector("[data-password-strength-input]");
        if (!strengthPanel || !passwordInput) {
            return;
        }

        const items = strengthPanel.querySelectorAll("[data-rule]");

        function updateStrength() {
            const value = passwordInput.value;
            const results = evaluatePassword(value);

            if (value.length > 0) {
                strengthPanel.classList.add("is-visible");
            } else {
                strengthPanel.classList.remove("is-visible");
            }

            items.forEach(function (item) {
                const rule = item.getAttribute("data-rule");
                item.classList.toggle("is-met", Boolean(results[rule]));
            });
        }

        passwordInput.addEventListener("input", updateStrength);
        passwordInput.addEventListener("focus", updateStrength);
        updateStrength();
    }

    function initAuthForms() {
        const screen = document.querySelector(".auth-screen");
        if (!screen) {
            return;
        }
        initPasswordToggles(screen);
        initPasswordStrength(screen);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAuthForms);
    } else {
        initAuthForms();
    }
})();
