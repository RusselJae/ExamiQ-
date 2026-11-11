/**
 * EXAMIQ global UI — toasts and Django message conversion
 */
(function () {
    "use strict";

    // Shared KaTeX auto-render options (\\hl highlight macro, trust for \\htmlClass).
    window.ExamiQKatex = window.ExamiQKatex || {};
    window.ExamiQKatex.options = {
        delimiters: [
            { left: "$$", right: "$$", display: true },
            { left: "$", right: "$", display: false },
        ],
        throwOnError: false,
        trust: function (context) {
            return context.command === "\\htmlClass";
        },
        macros: {
            "\\hl": "\\htmlClass{tutor-visual-mark}{#1}",
        },
    };

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
            "toast-item " + (TOAST_BORDER[type] || TOAST_BORDER.info);
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
            "banner-item toast-item " + (TOAST_BORDER[type] || TOAST_BORDER.info);
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

    const CONFIRM_TYPES = {
        warning: "confirm-dialog-card--warning",
        error: "confirm-dialog-card--error",
        danger: "confirm-dialog-card--error",
        info: "confirm-dialog-card--info",
    };

    const CONFIRM_ICONS = {
        warning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        deactivate: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="17" y1="8" x2="23" y2="14"/><line x1="23" y1="8" x2="17" y2="14"/></svg>',
        activate: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><polyline points="16 11 18 13 22 9"/></svg>',
        archive: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8"/><line x1="10" y1="12" x2="14" y2="12"/></svg>',
        restore: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 7 3 13 9 13"/><path d="M3.5 13a9 9 0 1 0 2.1-9.4L3 7"/></svg>',
        remove: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>',
        exit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>',
        approve: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><polyline points="8 12.5 11 15.5 16.5 9"/></svg>',
        reject: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><line x1="9" y1="9" x2="15" y2="15"/><line x1="15" y1="9" x2="9" y2="15"/></svg>',
    };

    window.showConfirm = function (options) {
        options = options || {};
        const root = document.getElementById("confirm-dialog-root");
        if (!root) return Promise.resolve(false);

        const titleEl = root.querySelector("#confirm-dialog-title");
        const messageEl = root.querySelector("#confirm-dialog-message");
        const iconEl = root.querySelector("#confirm-dialog-icon");
        const card = root.querySelector(".confirm-dialog-card");
        const okBtn = root.querySelector("[data-confirm-ok]");
        const cancelLabelBtn = root.querySelector("[data-confirm-cancel-btn]");
        const cancelTriggers = root.querySelectorAll("[data-confirm-cancel]");
        if (!messageEl || !card || !okBtn) return Promise.resolve(false);

        const type = options.type || "warning";
        card.className =
            "confirm-dialog-card " + (CONFIRM_TYPES[type] || CONFIRM_TYPES.warning);
        if (iconEl) {
            iconEl.innerHTML =
                CONFIRM_ICONS[options.icon] || CONFIRM_ICONS[type] || CONFIRM_ICONS.warning;
        }
        if (titleEl) {
            titleEl.textContent = options.title || "Confirm";
        }
        messageEl.textContent = options.message || "Are you sure?";
        okBtn.textContent = options.confirmLabel || "Confirm";
        if (cancelLabelBtn) {
            cancelLabelBtn.textContent = options.cancelLabel || "Cancel";
        }

        root.classList.remove("hidden");
        root.setAttribute("aria-hidden", "false");
        okBtn.focus();

        return new Promise(function (resolve) {
            function cleanup(result) {
                root.classList.add("hidden");
                root.setAttribute("aria-hidden", "true");
                okBtn.removeEventListener("click", onOk);
                cancelTriggers.forEach(function (el) {
                    el.removeEventListener("click", onCancel);
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
            cancelTriggers.forEach(function (el) {
                el.addEventListener("click", onCancel);
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
        if (params.get("archived") === "1") {
            showToast(
                "This account has been archived. Contact your program coordinator to restore access.",
                "error"
            );
        }
    }

    function initUi() {
        initDjangoMessages();
        initAuthBanners();
        initProfileDropdowns();
        initAppSidebar();
        initConfirmForms();
        initConfirmLinks();
        initKebabMenus();
        initMobileNavSearch();
        initTopbarHeight();
    }

    /* Also boot immediately when the document is already parsed, otherwise a
       script loaded after DOMContentLoaded never initialises. */
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initUi);
    } else {
        initUi();
    }

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
                    title: form.dataset.confirmTitle || "Confirm",
                    type: type,
                    icon: form.dataset.confirmIcon || "",
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

    function initConfirmLinks() {
        document.querySelectorAll("a[data-confirm-message]").forEach(function (link) {
            if (link.dataset.confirmBound) return;
            link.dataset.confirmBound = "1";
            link.addEventListener("click", function (event) {
                if (link.dataset.confirmed === "1") {
                    link.dataset.confirmed = "0";
                    return;
                }
                event.preventDefault();
                showConfirm({
                    message: link.dataset.confirmMessage,
                    title: link.dataset.confirmTitle || "Leave page?",
                    type: link.dataset.confirmType || "warning",
                    icon: link.dataset.confirmIcon || "exit",
                    confirmLabel: link.dataset.confirmLabel || "Leave",
                    cancelLabel: link.dataset.cancelLabel || "Stay",
                }).then(function (ok) {
                    if (ok) {
                        link.dataset.confirmed = "1";
                        window.location.href = link.href;
                    }
                });
            });
        });
    }

    function initKebabMenus() {
        function closeAll(except) {
            document.querySelectorAll(".account-kebab[open]").forEach(function (details) {
                if (details !== except) details.removeAttribute("open");
            });
        }

        function position(details) {
            const menu = details.querySelector(".account-kebab__menu");
            const trigger = details.querySelector("summary");
            if (!menu || !trigger) return;
            menu.style.visibility = "hidden";
            menu.classList.add("account-kebab__menu--floating");
            const rect = trigger.getBoundingClientRect();
            const width = menu.offsetWidth || 180;
            const height = menu.offsetHeight || 120;
            let left = Math.min(rect.right - width, window.innerWidth - width - 8);
            left = Math.max(8, left);
            let top = rect.bottom + 6;
            if (top + height > window.innerHeight - 8) {
                top = Math.max(8, rect.top - height - 6);
            }
            menu.style.left = left + "px";
            menu.style.top = top + "px";
            menu.style.right = "auto";
            menu.style.visibility = "";
        }

        function reset(details) {
            const menu = details.querySelector(".account-kebab__menu");
            if (!menu) return;
            menu.classList.remove("account-kebab__menu--floating");
            menu.style.left = "";
            menu.style.top = "";
            menu.style.right = "";
            menu.style.visibility = "";
        }

        document.addEventListener(
            "toggle",
            function (event) {
                const details = event.target;
                if (!details || !details.classList || !details.classList.contains("account-kebab")) return;
                if (details.open) {
                    closeAll(details);
                    position(details);
                } else {
                    reset(details);
                }
            },
            true
        );

        document.addEventListener("click", function (event) {
            if (!event.target.closest(".account-kebab")) closeAll();
        });
        window.addEventListener("resize", function () { closeAll(); });
        window.addEventListener("scroll", function () { closeAll(); }, true);
    }

    function closeAllNavElements() {
        // Close profile dropdowns
        document.querySelectorAll("[data-dropdown].open").forEach(function (dropdown) {
            dropdown.classList.remove("open");
            var menu = dropdown.querySelector("[data-dropdown-menu]");
            var toggle = dropdown.querySelector("[data-dropdown-toggle]");
            if (menu) menu.classList.add("hidden");
            if (toggle) toggle.setAttribute("aria-expanded", "false");
        });

        // Close notifications dropdown
        document.querySelectorAll("[data-notifications-dropdown]").forEach(function (root) {
            var menu = root.querySelector("[data-notifications-menu]");
            var toggle = root.querySelector("[data-notifications-toggle]");
            if (menu) menu.classList.add("hidden");
            if (toggle) toggle.setAttribute("aria-expanded", "false");
        });

        // Close mobile search floating
        var floating = document.getElementById("nav-search-floating");
        var searchToggle = document.querySelector("[data-nav-search-toggle]");
        if (floating && !floating.classList.contains("hidden")) {
            floating.classList.add("hidden");
            if (searchToggle) searchToggle.setAttribute("aria-expanded", "false");
        }

        // Close chat modal
        var chatModal = document.getElementById("examiq-chat-modal");
        if (chatModal && !chatModal.classList.contains("hidden")) {
            chatModal.classList.add("hidden");
            document.documentElement.classList.remove("examiq-chat-open");
        }
        document.querySelectorAll("[data-open-chat-modal]").forEach(function (el) {
            el.classList.remove("is-active");
        });

        // Close AI tutor modal
        var aiTutorModal = document.getElementById("ai-tutor-modal");
        if (aiTutorModal && !aiTutorModal.classList.contains("hidden")) {
            aiTutorModal.classList.add("hidden");
            document.body.classList.remove("ai-tutor-modal-open");
        }
        document.querySelectorAll("[data-open-ai-tutor]").forEach(function (el) {
            el.classList.remove("is-active");
        });
    }

    // Expose globally for other modules
    window.ExamiQCloseAllNavElements = closeAllNavElements;

    /* Publish the height of the fixed top bar so the page content can be
       offset by exactly the right amount. */
    function initTopbarHeight() {
        var topbar = document.getElementById("app-topbar");
        if (!topbar) return;
        function update() {
            var height = topbar.getBoundingClientRect().height;
            document.documentElement.style.setProperty(
                "--app-topbar-h",
                height + "px"
            );
        }
        update();
        window.addEventListener("resize", update);
        window.addEventListener("orientationchange", update);
        if (window.ResizeObserver) {
            new ResizeObserver(update).observe(topbar);
        }
    }

    function initMobileNavSearch() {
        var toggle = document.querySelector("[data-nav-search-toggle]");
        var floating = document.getElementById("nav-search-floating");
        if (!toggle || !floating) return;
        function setSearchOpen(isOpen) {
            floating.classList.toggle("hidden", !isOpen);
            toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
            if (isOpen) {
                var input = floating.querySelector("input");
                if (input) input.focus();
            }
        }
        toggle.addEventListener("click", function (e) {
            e.stopPropagation();
            var willOpen = floating.classList.contains("hidden");
            if (willOpen) {
                closeAllNavElements();
            }
            setSearchOpen(willOpen);
        });
        document.addEventListener("click", function (e) {
            if (floating.classList.contains("hidden")) return;
            if (e.target.closest && e.target.closest("#nav-search-floating")) return;
            if (e.target.closest && e.target.closest("[data-nav-search-toggle]")) return;
            setSearchOpen(false);
        });
    }

    function initProfileDropdowns() {
        document.querySelectorAll("[data-dropdown]").forEach(function (dropdown) {
            const toggle = dropdown.querySelector("[data-dropdown-toggle]");
            const menu = dropdown.querySelector("[data-dropdown-menu]");
            if (!toggle || !menu) return;

            toggle.addEventListener("click", function (e) {
                e.stopPropagation();
                /* Section toggles (e.g. sidebar "Action Plan") only reveal their
                   sub-links; the sub-items carry the navigation. */
                if (toggle.hasAttribute("data-dropdown-prevent-nav")) {
                    e.preventDefault();
                }
                const isOpen = dropdown.classList.contains("open");
                closeAllNavElements();
                if (!isOpen) {
                    openDropdown(dropdown);
                }
            });

            /* Sticky menus behave like an expanded section: open on load and
               only collapse when their toggle is clicked again. */
            if (dropdown.hasAttribute("data-dropdown-sticky")) {
                openDropdown(dropdown);
            }
        });

        document.addEventListener("click", function () {
            /* Sticky menus (the sidebar "Action Plan" section) behave like an
               expanded section: they stay open until their own toggle is
               clicked again, so skip dismiss-on-outside-click entirely. */
            if (document.querySelector("[data-dropdown-sticky].open")) return;
            /* Only close profile dropdowns here. The notifications dropdown
               owns its own outside-click handler, and it runs before this
               one — closing it here would immediately dismiss the panel the
               user just opened. */
            closeAllDropdowns();
        });

        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape") closeAllNavElements();
        });
    }

    function openDropdown(dropdown) {
        dropdown.classList.add("open");
        const menu = dropdown.querySelector("[data-dropdown-menu]");
        const toggle = dropdown.querySelector("[data-dropdown-toggle]");
        if (menu) menu.classList.remove("hidden");
        if (toggle) toggle.setAttribute("aria-expanded", "true");
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
                /* Mobile only: the button opens/closes the slide-in drawer.
                   On desktop the sidebar's own chevron handles collapsing. */
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

        /* My Courses live filter: match group code/title, hide empty buckets. */
        sidebar.querySelectorAll("[data-sidebar-filter]").forEach(function (input) {
            if (input.dataset.bound) return;
            input.dataset.bound = "1";
            var section = input.closest(".sidebar-course-section");
            var clearBtn = section
                ? section.querySelector("[data-sidebar-clear]")
                : null;
            function applyFilter() {
                var q = (input.value || "").trim().toLowerCase();
                if (!section) return;
                if (clearBtn) clearBtn.hidden = !input.value;
                var groups = section.querySelectorAll("[data-sidebar-group]");
                if (groups.length) {
                    groups.forEach(function (group) {
                        var visible = 0;
                        group.querySelectorAll("[data-sidebar-course]").forEach(function (item) {
                            var text = (item.textContent || "").toLowerCase();
                            var match = !q || text.indexOf(q) !== -1;
                            item.style.display = match ? "" : "none";
                            if (match) visible += 1;
                        });
                        group.style.display = visible ? "" : "none";
                    });
                    return;
                }
                section.querySelectorAll("[data-sidebar-list] [data-sidebar-course]").forEach(function (item) {
                    var text = (item.textContent || "").toLowerCase();
                    var match = !q || text.indexOf(q) !== -1;
                    item.style.display = match ? "" : "none";
                });
            }
            input.addEventListener("input", applyFilter);
            if (clearBtn && !clearBtn.dataset.bound) {
                clearBtn.dataset.bound = "1";
                clearBtn.addEventListener("click", function () {
                    input.value = "";
                    applyFilter();
                    input.focus();
                });
            }
        });

        /* Collapsible sidebar course buckets (Pinned / This Semester / Earlier). */
        sidebar.querySelectorAll("[data-sidebar-toggle]").forEach(function (btn) {
            if (btn.dataset.bound) return;
            btn.dataset.bound = "1";
            btn.addEventListener("click", function () {
                const group = btn.closest("[data-sidebar-group]");
                const list = group ? group.querySelector("[data-sidebar-list]") : null;
                if (!list) return;
                const collapsed = list.classList.toggle("hidden");
                btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
                try {
                    sessionStorage.setItem(
                        "examiq.sidebar-group." + group.dataset.sidebarGroup,
                        collapsed ? "1" : "0"
                    );
                } catch (e) { /* ignore */ }
            });
        });
        sidebar.querySelectorAll("[data-sidebar-group]").forEach(function (group) {
            const key = group.dataset.sidebarGroup;
            let stored = null;
            try {
                stored = sessionStorage.getItem("examiq.sidebar-group." + key);
            } catch (e) { /* ignore */ }
            if (stored === null) return;
            const list = group.querySelector("[data-sidebar-list]");
            const btn = group.querySelector("[data-sidebar-toggle]");
            if (!list || !btn) return;
            list.classList.toggle("hidden", stored === "1");
            btn.setAttribute("aria-expanded", stored === "1" ? "false" : "true");
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

        if (labels.length < 1) {
            if (wrapEl) wrapEl.classList.add("hidden");
            if (emptyEl) emptyEl.classList.remove("hidden");
            return;
        }

        if (wrapEl) wrapEl.classList.remove("hidden");
        if (emptyEl) emptyEl.classList.add("hidden");

        function scoreColor(score) {
            if (score < 60) return "#F57C00";
            if (score < 75) return "#0284C7";
            return "#388E3C";
        }

        new Chart(canvas, {
            type: "bar",
            data: {
                labels: labels,
                datasets: [{
                    label: "Score %",
                    data: values,
                    backgroundColor: values.map(scoreColor),
                    borderRadius: 6,
                    maxBarThickness: 36,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { min: 0, max: 100, grid: { color: "#f1f5f9" } },
                    x: { grid: { display: false } }
                },
                plugins: { legend: { display: false } }
            }
        });
    };

    window.ExamiQUI.renderConfidencePerformanceChart = function (canvas, seriesData, options) {
        options = options || {};
        const emptyEl = options.emptyEl;
        const wrapEl = options.wrapEl;
        if (!canvas || typeof Chart === "undefined") return;

        const data = seriesData || [];
        if (data.length < 1) {
            if (wrapEl) wrapEl.classList.add("hidden");
            if (emptyEl) emptyEl.classList.remove("hidden");
            return;
        }

        if (wrapEl) wrapEl.classList.remove("hidden");
        if (emptyEl) emptyEl.classList.add("hidden");

        new Chart(canvas, {
            type: "bar",
            data: {
                labels: data.map(function (d) { return d.label; }),
                datasets: [
                    {
                        label: "Confidence (0–3)",
                        data: data.map(function (d) { return d.confidence; }),
                        backgroundColor: "#F57C00",
                        borderRadius: 4,
                        yAxisID: "yConfidence",
                    },
                    {
                        label: "Performance (%)",
                        data: data.map(function (d) { return d.performance; }),
                        backgroundColor: "#388E3C",
                        borderRadius: 4,
                        yAxisID: "yPerformance",
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    yConfidence: {
                        type: "linear",
                        position: "left",
                        min: 0,
                        max: 3,
                        ticks: { stepSize: 1, precision: 0 },
                        grid: { color: "#f1f5f9" },
                        title: { display: true, text: "Confidence (0–3)" },
                    },
                    yPerformance: {
                        type: "linear",
                        position: "right",
                        min: 0,
                        max: 100,
                        grid: { drawOnChartArea: false },
                        title: { display: true, text: "Performance (%)" },
                    },
                    x: { grid: { display: false }, ticks: { maxRotation: 45, minRotation: 0 } },
                },
                plugins: {
                    legend: {
                        display: true,
                        position: "bottom",
                        align: "center",
                    },
                },
            },
        });
    };

    document.body.addEventListener("showToast", function (event) {
        const detail = event.detail;
        if (detail && detail.message) {
            showToast(detail.message, detail.type || "info");
        }
    });
})();
