/**
 * EXAMIQ global UI — toasts and Django message conversion
 */
(function () {
    "use strict";

    const TOAST_DURATION = 4000;

    const TOAST_BORDER = {
        success: "toast-item--success",
        error: "toast-item--error",
        info: "toast-item--info",
        warning: "toast-item--warning",
    };

    function getToastStack() {
        return document.getElementById("toast-stack");
    }

    function dismissToast(toast) {
        if (!toast || toast.classList.contains("toast-dismissing")) return;
        toast.classList.add("toast-dismissing");
        setTimeout(function () {
            toast.remove();
        }, 300);
    }

    window.showToast = function (message, type) {
        type = type || "info";
        const stack = getToastStack();
        if (!stack) return;

        const toast = document.createElement("div");
        toast.className =
            "toast-item pointer-events-auto px-4 py-3 pr-10 text-sm text-slate-800 relative " +
            (TOAST_BORDER[type] || TOAST_BORDER.info);
        toast.setAttribute("role", "alert");

        const messageEl = document.createElement("span");
        messageEl.className = "toast-message";
        messageEl.textContent = message;
        toast.appendChild(messageEl);

        const closeBtn = document.createElement("button");
        closeBtn.type = "button";
        closeBtn.className = "toast-close";
        closeBtn.setAttribute("aria-label", "Dismiss");
        closeBtn.innerHTML = "&times;";
        closeBtn.addEventListener("click", function () {
            dismissToast(toast);
        });
        toast.appendChild(closeBtn);

        stack.appendChild(toast);

        setTimeout(function () {
            dismissToast(toast);
        }, TOAST_DURATION);
    };

    function getBannerStack() {
        return document.getElementById("banner-stack");
    }

    function dismissBanner(banner) {
        if (!banner || banner.classList.contains("banner-dismissing")) return;
        banner.classList.add("banner-dismissing");
        setTimeout(function () {
            banner.remove();
        }, 300);
    }

    window.showBanner = function (message, type) {
        type = type || "info";
        const stack = getBannerStack();
        if (!stack) return;

        const banner = document.createElement("div");
        banner.className =
            "banner-item toast-item pointer-events-auto px-4 py-3 pr-10 text-sm text-slate-800 relative " +
            (TOAST_BORDER[type] || TOAST_BORDER.info);
        banner.setAttribute("role", "alert");

        const messageEl = document.createElement("span");
        messageEl.className = "toast-message";
        messageEl.textContent = message;
        banner.appendChild(messageEl);

        const closeBtn = document.createElement("button");
        closeBtn.type = "button";
        closeBtn.className = "toast-close";
        closeBtn.setAttribute("aria-label", "Dismiss");
        closeBtn.innerHTML = "&times;";
        closeBtn.addEventListener("click", function () {
            dismissBanner(banner);
        });
        banner.appendChild(closeBtn);

        stack.appendChild(banner);

        setTimeout(function () {
            dismissBanner(banner);
        }, TOAST_DURATION);
    };

    const CONFIRM_BORDER = {
        warning: "toast-item--warning",
        error: "toast-item--error",
        info: "toast-item--info",
    };

    window.showConfirm = function (options) {
        options = options || {};
        const root = document.getElementById("confirm-dialog-root");
        if (!root) return Promise.resolve(false);

        const messageEl = root.querySelector("#confirm-dialog-message");
        const card = root.querySelector(".confirm-dialog-card");
        const okBtn = root.querySelector("[data-confirm-ok]");
        const cancelBtns = root.querySelectorAll("[data-confirm-cancel]");
        if (!messageEl || !card || !okBtn) return Promise.resolve(false);

        const type = options.type || "warning";
        card.className =
            "confirm-dialog-card toast-item " + (CONFIRM_BORDER[type] || CONFIRM_BORDER.warning);
        messageEl.textContent = options.message || "Are you sure?";
        okBtn.textContent = options.confirmLabel || "Confirm";
        cancelBtns.forEach(function (btn) {
            btn.textContent = options.cancelLabel || "Cancel";
        });

        root.classList.remove("hidden");
        root.setAttribute("aria-hidden", "false");
        okBtn.focus();

        return new Promise(function (resolve) {
            function cleanup(result) {
                root.classList.add("hidden");
                root.setAttribute("aria-hidden", "true");
                okBtn.removeEventListener("click", onOk);
                cancelBtns.forEach(function (btn) {
                    btn.removeEventListener("click", onCancel);
                });
                document.removeEventListener("keydown", onKeydown);
                resolve(result);
            }

            function onOk() {
                cleanup(true);
            }

            function onCancel() {
                cleanup(false);
            }

            function onKeydown(e) {
                if (e.key === "Escape") onCancel();
            }

            okBtn.addEventListener("click", onOk);
            cancelBtns.forEach(function (btn) {
                btn.addEventListener("click", onCancel);
            });
            document.addEventListener("keydown", onKeydown);
        });
    };

    function isAuthScreen() {
        return (
            document.body.classList.contains("auth-page") ||
            document.body.classList.contains("landing-body")
        );
    }

    function initDjangoMessages() {
        const container = document.getElementById("django-messages");
        if (!container) return;
        container.querySelectorAll("[data-toast-message]").forEach(function (el) {
            const msg = el.dataset.toastMessage || "";
            const onAuthScreen = isAuthScreen();
            if (!onAuthScreen && /signed out/i.test(msg)) {
                return;
            }
            let type = el.dataset.toastType || "info";
            if (type === "error") type = "error";
            else if (type === "success") type = "success";
            else if (type === "warning") type = "warning";
            else type = "info";
            showToast(msg, type);
        });
    }

    function initAuthBanners() {
        const params = new URLSearchParams(window.location.search);
        const registered = params.get("registered");
        if (registered === "pending") {
            showToast(
                "Account submitted. A campus administrator will review your request before you can sign in.",
                "info"
            );
        } else if (registered === "rejected") {
            showToast(
                "Your registration was not approved. Contact your campus administrator for help.",
                "error"
            );
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        initDjangoMessages();
        initAuthBanners();
        initProfileDropdowns();
        initAppSidebar();
        initConfirmForms();
    });

    function initConfirmForms() {
        document.querySelectorAll("form[data-confirm-message]").forEach(function (form) {
            if (form.dataset.confirmBound) return;
            form.dataset.confirmBound = "1";
            form.addEventListener("submit", function (e) {
                if (form.dataset.confirmed === "1") {
                    form.dataset.confirmed = "0";
                    return;
                }
                e.preventDefault();
                const message = form.dataset.confirmMessage;
                const type = form.dataset.confirmType || "warning";
                showConfirm({
                    message: message,
                    type: type,
                    confirmLabel: form.dataset.confirmLabel || "Confirm",
                    cancelLabel: form.dataset.cancelLabel || "Cancel",
                }).then(function (ok) {
                    if (ok) {
                        form.dataset.confirmed = "1";
                        form.requestSubmit();
                    }
                });
            });
        });
    }

    function initProfileDropdowns() {
        document.querySelectorAll("[data-dropdown]").forEach(function (dropdown) {
            const toggle = dropdown.querySelector("[data-dropdown-toggle]");
            const menu = dropdown.querySelector("[data-dropdown-menu]");
            if (!toggle || !menu) return;

            toggle.addEventListener("click", function (e) {
                e.stopPropagation();
                const isOpen = dropdown.classList.contains("open");
                closeAllDropdowns();
                if (!isOpen) {
                    dropdown.classList.add("open");
                    menu.classList.remove("hidden");
                    toggle.setAttribute("aria-expanded", "true");
                }
            });
        });

        document.addEventListener("click", function () {
            closeAllDropdowns();
        });

        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape") closeAllDropdowns();
        });
    }

    function closeAllDropdowns() {
        document.querySelectorAll("[data-dropdown].open").forEach(function (dropdown) {
            dropdown.classList.remove("open");
            const menu = dropdown.querySelector("[data-dropdown-menu]");
            const toggle = dropdown.querySelector("[data-dropdown-toggle]");
            if (menu) menu.classList.add("hidden");
            if (toggle) toggle.setAttribute("aria-expanded", "false");
        });
    }

    function initAppSidebar() {
        const sidebar = document.getElementById("app-sidebar");
        const backdrop = document.getElementById("sidebar-backdrop");
        const toggleBtn = document.getElementById("sidebar-toggle-mobile");
        const collapseBtn = document.getElementById("sidebar-collapse-toggle");
        if (!sidebar) return;

        const STORAGE_KEY = "examiq.sidebar.collapsed";

        function openSidebar() {
            sidebar.classList.add("open");
            if (backdrop) backdrop.classList.remove("hidden");
        }

        function closeSidebar() {
            sidebar.classList.remove("open");
            if (backdrop) backdrop.classList.add("hidden");
        }

        function setCollapsed(collapsed) {
            sidebar.classList.toggle("is-collapsed", collapsed);
            if (collapseBtn) {
                collapseBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
                collapseBtn.setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar");
            }
            try {
                localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
            } catch (e) { /* ignore */ }
        }

        try {
            if (localStorage.getItem(STORAGE_KEY) === "1" && window.innerWidth >= 1024) {
                setCollapsed(true);
            }
        } catch (e) { /* ignore */ }

        if (toggleBtn) {
            toggleBtn.addEventListener("click", function () {
                if (sidebar.classList.contains("open")) {
                    closeSidebar();
                } else {
                    openSidebar();
                }
            });
        }

        if (collapseBtn) {
            collapseBtn.addEventListener("click", function () {
                setCollapsed(!sidebar.classList.contains("is-collapsed"));
            });
        }

        if (backdrop) {
            backdrop.addEventListener("click", closeSidebar);
        }

        sidebar.querySelectorAll(".sidebar-link").forEach(function (link) {
            link.addEventListener("click", function () {
                if (window.innerWidth < 1024) closeSidebar();
            });
        });
    }

    window.ExamiQUI = window.ExamiQUI || {};

    window.ExamiQUI.setButtonLoading = function (btn, isLoading, loadingText) {
        if (!btn) return;
        if (isLoading) {
            if (!btn.dataset.originalHtml) {
                btn.dataset.originalHtml = btn.innerHTML;
            }
            btn.disabled = true;
            btn.classList.add("btn-loading");
            btn.setAttribute("aria-busy", "true");
            const label = loadingText || "Loading…";
            btn.innerHTML =
                '<span class="btn-spinner" aria-hidden="true"></span><span>' + label + "</span>";
        } else {
            btn.disabled = false;
            btn.classList.remove("btn-loading");
            btn.removeAttribute("aria-busy");
            if (btn.dataset.originalHtml) {
                btn.innerHTML = btn.dataset.originalHtml;
            }
        }
    };

    window.ExamiQUI.renderAccuracyChart = function (canvas, trendData, options) {
        options = options || {};
        const emptyEl = options.emptyEl;
        const wrapEl = options.wrapEl;
        if (!canvas || typeof Chart === "undefined") return;

        const labels = (trendData || []).map(function (d) { return d.date; });
        const values = (trendData || []).map(function (d) { return d.accuracy; });

        if (labels.length < 2) {
            if (wrapEl) wrapEl.classList.add("hidden");
            if (emptyEl) emptyEl.classList.remove("hidden");
            return;
        }

        if (wrapEl) wrapEl.classList.remove("hidden");
        if (emptyEl) emptyEl.classList.add("hidden");

        new Chart(canvas, {
            type: "line",
            data: {
                labels: labels,
                datasets: [{
                    label: "Accuracy %",
                    data: values,
                    borderColor: "#2E7D52",
                    backgroundColor: "rgba(46, 125, 82, 0.12)",
                    tension: 0.3,
                    fill: true,
                }]
            },
            options: {
                scales: {
                    y: { min: 0, max: 100, grid: { color: "#f1f5f9" } },
                    x: { grid: { display: false } }
                },
                plugins: { legend: { display: false } }
            }
        });
    };

    document.body.addEventListener("showToast", function (event) {
        const detail = event.detail;
        if (detail && detail.message) {
            showToast(detail.message, detail.type || "info");
        }
    });
})();
