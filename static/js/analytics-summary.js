/**
 * Global professor course summary widget — generate, recall, refresh, close.
 */
(function () {
    "use strict";

    const LAST_COURSE_KEY = "examiq.summary.lastCoursePk";
    const CACHE_PREFIX = "examiq.summary.";

    function cacheKey(pk) {
        return CACHE_PREFIX + pk;
    }

    function getCourses() {
        const el = document.getElementById("summary-courses-data");
        if (!el) return [];
        try {
            const parsed = JSON.parse(el.textContent);
            return Array.isArray(parsed) ? parsed : [];
        } catch (e) {
            return [];
        }
    }

    function getCookie(name) {
        const match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
        return match ? decodeURIComponent(match[1]) : "";
    }

    function getCsrfToken() {
        const hidden = document.getElementById("summary-csrf");
        if (hidden && hidden.value) return hidden.value;
        const input = document.querySelector("[name=csrfmiddlewaretoken]");
        if (input && input.value) return input.value;
        return getCookie("csrftoken");
    }

    function storageGet(key) {
        try {
            return sessionStorage.getItem(key);
        } catch (e) {
            return null;
        }
    }

    function storageSet(key, value) {
        try {
            sessionStorage.setItem(key, value);
        } catch (e) { /* ignore */ }
    }

    function resolveCoursePk(root, courses) {
        if (!courses.length) return null;
        const sidebarPk = root.dataset.sidebarCoursePk;
        if (sidebarPk) return String(sidebarPk);
        const last = storageGet(LAST_COURSE_KEY);
        if (last && courses.some(function (c) { return String(c.pk) === last; })) {
            return last;
        }
        return String(courses[0].pk);
    }

    function loadCache(pk) {
        try {
            const raw = storageGet(cacheKey(pk));
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            return null;
        }
    }

    function saveCache(pk, data) {
        try {
            storageSet(cacheKey(pk), JSON.stringify(data));
            storageSet(LAST_COURSE_KEY, String(pk));
        } catch (e) { /* ignore */ }
    }

    function findCourse(courses, pk) {
        return courses.find(function (c) { return String(c.pk) === String(pk); }) || null;
    }

    function generateUrl(root, pk) {
        const pattern = root.dataset.generateUrlPattern;
        if (pattern) {
            return pattern.replace("/0/", "/" + pk + "/");
        }
        return "/professor/courses/" + pk + "/summary/generate/";
    }

    function formatTimestamp(iso) {
        if (!iso) return "";
        try {
            return new Date(iso).toLocaleString(undefined, {
                month: "short",
                day: "numeric",
                year: "numeric",
                hour: "numeric",
                minute: "2-digit",
            });
        } catch (e) {
            return "";
        }
    }

    function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text || "";
        return div.innerHTML;
    }

    document.addEventListener("DOMContentLoaded", function () {
        const root = document.getElementById("summary-widget-root");
        if (!root) return;

        const courses = getCourses();
        if (!courses.length) return;

        const panel = document.getElementById("summary-panel");
        const content = document.getElementById("summary-panel-content");
        const timestamp = document.getElementById("summary-panel-timestamp");
        const courseLabel = document.getElementById("summary-panel-course");
        const fab = document.getElementById("summary-fab");
        const recallBtn = document.getElementById("summary-recall-btn");
        const refreshBtn = document.getElementById("summary-refresh-btn");
        const closeBtn = document.getElementById("summary-close-btn");
        const pickerWrap = document.getElementById("summary-course-picker-wrap");
        const picker = document.getElementById("summary-course-picker");
        const csrfHidden = document.getElementById("summary-csrf");

        const csrfFromPage = document.querySelector("[name=csrfmiddlewaretoken]");
        if (csrfFromPage && csrfHidden) {
            csrfHidden.value = csrfFromPage.value;
        }

        let activePk = resolveCoursePk(root, courses);
        let loading = false;

        function needsPicker() {
            return !root.dataset.sidebarCoursePk && !storageGet(LAST_COURSE_KEY);
        }

        function populatePicker() {
            if (!picker) return;
            picker.innerHTML = "";
            courses.forEach(function (c) {
                const opt = document.createElement("option");
                opt.value = c.pk;
                opt.textContent = c.label;
                picker.appendChild(opt);
            });
            picker.value = activePk;
        }

        if (needsPicker() && courses.length > 1) {
            pickerWrap.classList.remove("hidden");
            populatePicker();
        }

        function updateCourseLabel() {
            const course = findCourse(courses, activePk);
            if (courseLabel && course) {
                courseLabel.textContent = course.label;
            }
        }

        function openPanel() {
            panel.classList.add("is-open");
            panel.setAttribute("aria-hidden", "false");
        }

        function closePanel() {
            panel.classList.remove("is-open");
            panel.setAttribute("aria-hidden", "true");
        }

        function showLoading() {
            content.innerHTML =
                '<div class="summary-panel-loading">' +
                '<span class="btn-spinner" style="border-color:#1A5632;border-top-color:transparent"></span>' +
                "<span>Generating summary…</span></div>";
            timestamp.classList.add("hidden");
        }

        function renderCached(data) {
            if (!data || !data.narrative) {
                content.innerHTML =
                    '<p class="text-sm text-examiq-slate">No summary yet. Click the lightbulb to generate one.</p>';
                timestamp.classList.add("hidden");
                return;
            }
            let html = '<p class="summary-panel-narrative">' + escapeHtml(data.narrative) + "</p>";
            if (data.aiHint) {
                html = '<p class="summary-panel-ai-hint">' + escapeHtml(data.aiHint) + "</p>" + html;
            }
            content.innerHTML = html;
            if (data.generatedAt) {
                timestamp.textContent = "Generated " + formatTimestamp(data.generatedAt);
                timestamp.classList.remove("hidden");
            } else {
                timestamp.classList.add("hidden");
            }
        }

        async function generateSummary() {
            if (loading) return;
            loading = true;
            openPanel();
            updateCourseLabel();
            showLoading();

            try {
                const resp = await fetch(generateUrl(root, activePk), {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "X-CSRFToken": getCsrfToken(),
                        "X-Requested-With": "XMLHttpRequest",
                    },
                });
                if (!resp.ok) throw new Error("Request failed");
                const data = await resp.json();
                const course = findCourse(courses, activePk);
                const cached = {
                    narrative: data.narrative || "",
                    generatedAt: new Date().toISOString(),
                    courseCode: course ? course.code : "",
                    aiHint: data.ai_enabled ? "" : "Enable AI in settings for richer recommendations.",
                };
                saveCache(activePk, cached);
                renderCached(cached);
            } catch (err) {
                content.innerHTML =
                    '<p class="text-sm text-examiq-coral">Could not generate summary. Please try again.</p>';
                timestamp.classList.add("hidden");
            } finally {
                loading = false;
            }
        }

        function showRecall() {
            activePk = resolveCoursePk(root, courses);
            if (picker) picker.value = activePk;
            updateCourseLabel();
            const cached = loadCache(activePk);
            openPanel();
            renderCached(cached);
        }

        updateCourseLabel();

        fab.addEventListener("click", generateSummary);
        refreshBtn.addEventListener("click", generateSummary);
        recallBtn.addEventListener("click", showRecall);
        closeBtn.addEventListener("click", closePanel);

        if (picker) {
            picker.addEventListener("change", function () {
                activePk = picker.value;
                storageSet(LAST_COURSE_KEY, String(activePk));
                updateCourseLabel();
                const cached = loadCache(activePk);
                if (cached) {
                    renderCached(cached);
                } else {
                    content.innerHTML =
                        '<p class="text-sm text-examiq-slate">No summary for this course yet. Click the lightbulb to generate.</p>';
                    timestamp.classList.add("hidden");
                }
            });
        }

        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape" && panel.classList.contains("is-open")) {
                closePanel();
            }
        });
    });
})();
