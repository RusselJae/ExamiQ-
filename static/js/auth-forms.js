/**
 * Auth form helpers — password visibility, strength, role cards, phone prefix.
 */
(function () {
    "use strict";

    function initPasswordToggles(root) {
        root.querySelectorAll("[data-password-field]").forEach(function (wrap) {
            const input = wrap.querySelector("input");
            const toggle = wrap.querySelector("[data-password-toggle]");
            if (!input || !toggle) return;

            const showIcon = toggle.querySelector(".auth-password-toggle__icon--show");
            const hideIcon = toggle.querySelector(".auth-password-toggle__icon--hide");

            toggle.addEventListener("click", function () {
                const isHidden = input.type === "password";
                input.type = isHidden ? "text" : "password";
                toggle.setAttribute("aria-pressed", isHidden ? "true" : "false");
                toggle.setAttribute("aria-label", isHidden ? "Hide password" : "Show password");
                if (showIcon) showIcon.classList.toggle("hidden", isHidden);
                if (hideIcon) hideIcon.classList.toggle("hidden", !isHidden);
            });
        });
    }

    function evaluatePassword(value) {
        const hasLength = value.length >= 8;
        const hasNumber = /\d/.test(value);
        const hasMixedCase = /[A-Z]/.test(value) && /[a-z]/.test(value);

        return {
            length: hasLength,
            mixed: hasNumber,
            special: hasMixedCase,
        };
    }

    function initPasswordStrength(root) {
        const strengthPanel = root.querySelector("[data-password-strength]");
        const passwordInput = root.querySelector("[data-password-strength-input]");
        if (!strengthPanel || !passwordInput) return;

        const items = strengthPanel.querySelectorAll("[data-rule]");

        function updateStrength() {
            const value = passwordInput.value;
            if (!value.length) {
                strengthPanel.classList.remove("is-visible");
                return;
            }

            strengthPanel.classList.add("is-visible");
            const results = evaluatePassword(value);
            items.forEach(function (item) {
                const rule = item.getAttribute("data-rule");
                item.classList.toggle("is-met", Boolean(results[rule]));
            });
        }

        passwordInput.addEventListener("input", updateStrength);
        passwordInput.addEventListener("focus", updateStrength);
        passwordInput.addEventListener("blur", function () {
            if (!passwordInput.value.length) {
                strengthPanel.classList.remove("is-visible");
            }
        });
    }

    function initSignupRoleCards(root) {
        const roleSelect = root.querySelector("#id_signup_role");
        const studentFields = root.querySelector("#signup-student-fields");
        const staffFields = root.querySelector("#signup-staff-fields");
        const roleCards = root.querySelectorAll(".auth-role-card");
        if (!roleSelect || !studentFields || !staffFields) return;

        function setRole(role) {
            roleSelect.value = role;
            roleCards.forEach(function (card) {
                card.classList.toggle("is-active", card.dataset.role === role);
            });
            const isStudent = role === "student";
            studentFields.classList.toggle("is-hidden", !isStudent);
            staffFields.classList.toggle("is-hidden", isStudent);
        }

        roleCards.forEach(function (card) {
            card.addEventListener("click", function () {
                setRole(card.dataset.role);
            });
        });

        setRole(roleSelect.value || "student");
    }

    function initPhonePrefix(root) {
        const display = root.querySelector("#id_phone_display");
        const hidden = root.querySelector("#id_phone_number");
        const form = root.querySelector("#signup-form");
        if (!display || !hidden) return;

        if (hidden.value && hidden.value.length === 11 && hidden.value.startsWith("0")) {
            display.value = hidden.value.slice(1);
        }

        function syncPhone() {
            const digits = display.value.replace(/\D/g, "");
            if (digits.length === 10 && digits.startsWith("9")) {
                hidden.value = "0" + digits;
            } else if (digits.length === 11 && digits.startsWith("09")) {
                hidden.value = digits;
            } else {
                hidden.value = digits;
            }
        }

        display.addEventListener("input", syncPhone);
        if (form) {
            form.addEventListener("submit", syncPhone);
        }
    }

    function initAuthForms() {
        const page = document.querySelector(".auth-page");
        if (!page) return;
        initPasswordToggles(page);
        initPasswordStrength(page);
        initSignupRoleCards(page);
        initPhonePrefix(page);
        initSectionCascade(page);
    }

    function initSectionCascade(root) {
        const yearSelect = root.querySelector("#id_year_level");
        const sectionSelect = root.querySelector("#id_section");
        if (!yearSelect || !sectionSelect) return;

        const programSelect = root.querySelector("#id_home_degree_program");
        const program =
            (programSelect && programSelect.value) ||
            sectionSelect.dataset.program ||
            "bsed_math";
        const sectionsUrl =
            sectionSelect.dataset.sectionsUrl || "/profile/api/sections/";

        async function loadSections() {
            const yearLevel = yearSelect.value;
            const currentValue = sectionSelect.value;
            sectionSelect.innerHTML = '<option value="">— Select section —</option>';
            if (!program || !yearLevel) return;

            try {
                const resp = await fetch(
                    sectionsUrl +
                        "?program=" +
                        encodeURIComponent(program) +
                        "&year_level=" +
                        yearLevel
                );
                const data = await resp.json();
                data.sections.forEach(function (section) {
                    const opt = document.createElement("option");
                    opt.value = section.id;
                    opt.textContent = section.is_full
                        ? section.display + " (Full)"
                        : section.display;
                    opt.disabled = section.is_full && String(section.id) !== currentValue;
                    if (String(section.id) === currentValue) {
                        opt.selected = true;
                    }
                    sectionSelect.appendChild(opt);
                });
            } catch (err) {
                /* ignore */
            }
        }

        if (programSelect) {
            programSelect.addEventListener("change", loadSections);
        }
        yearSelect.addEventListener("change", loadSections);
        loadSections();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAuthForms);
    } else {
        initAuthForms();
    }
})();
