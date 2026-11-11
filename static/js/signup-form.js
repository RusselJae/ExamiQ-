/**
 * Student signup: student-type switch, regular year/section picker, and the
 * irregular COR upload + analysis flow.
 */
(function () {
    "use strict";

    function readJson(id) {
        var el = document.getElementById(id);
        if (!el) return null;
        try {
            return JSON.parse(el.textContent);
        } catch (e) {
            return null;
        }
    }

    function escHtml(text) {
        return String(text == null ? "" : text).replace(/[&<>"']/g, function (c) {
            return {
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                '"': "&quot;",
                "'": "&#39;",
            }[c];
        });
    }

    var regularBtn = document.querySelector('.student-type-switch__btn[data-type="regular"]');
    var irregularBtn = document.querySelector('.student-type-switch__btn[data-type="irregular"]');
    var regularInput = document.getElementById("id_is_irregular-regular");
    var irregularInput = document.getElementById("id_is_irregular-irregular");
    var hiddenInput = document.getElementById("id_is_irregular");
    var regularFields = document.getElementById("regular-fields");
    var corWrapper = document.getElementById("cor-upload-wrapper");
    var irregularFields = document.getElementById("irregular-courses-wrapper");
    var yearLevel = document.getElementById("id_year_level");
    var sectionSelect = document.getElementById("id_section");
    var sectionHint = document.getElementById("section-hint");
    var sectionsByYear = readJson("sections-by-year") || {};

    function isIrregular() {
        return !!(irregularInput && irregularInput.checked);
    }

    function syncFaculty() {
        if (window.ExamiQSignupFaculty && window.ExamiQSignupFaculty.refresh) {
            window.ExamiQSignupFaculty.refresh();
        }
    }

    function setStudentType(irregular) {
        if (irregularInput) irregularInput.checked = irregular;
        if (regularInput) regularInput.checked = !irregular;
        if (hiddenInput) hiddenInput.value = irregular ? "1" : "0";
        if (regularBtn) {
            regularBtn.classList.toggle("student-type-switch__btn--active", !irregular);
            regularBtn.setAttribute("aria-pressed", String(!irregular));
        }
        if (irregularBtn) {
            irregularBtn.classList.toggle("student-type-switch__btn--active", irregular);
            irregularBtn.setAttribute("aria-pressed", String(irregular));
        }
        if (regularFields) regularFields.style.display = irregular ? "none" : "";
        if (corWrapper) corWrapper.style.display = irregular ? "" : "none";
        if (irregularFields) irregularFields.style.display = irregular ? "" : "none";
        if (yearLevel) {
            if (irregular) {
                yearLevel.removeAttribute("required");
            } else {
                yearLevel.setAttribute("required", "required");
            }
        }
        if (sectionSelect) {
            if (irregular) {
                sectionSelect.removeAttribute("required");
            } else {
                sectionSelect.setAttribute("required", "required");
            }
        }
        if (window.ExamiQSignupFaculty && window.ExamiQSignupFaculty.unlock) {
            window.ExamiQSignupFaculty.unlock();
        }
        syncFaculty();
    }

    function populateSections() {
        if (!sectionSelect) return;
        var yearId = yearLevel ? String(yearLevel.value || "") : "";
        var previous = sectionSelect.value;
        var options = (yearId && sectionsByYear[yearId]) || [];
        sectionSelect.innerHTML = "";
        var placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = options.length
            ? "— Select section —"
            : yearId
              ? "No sections configured for this year"
              : "— Select year level first —";
        sectionSelect.appendChild(placeholder);
        options.forEach(function (section) {
            var option = document.createElement("option");
            option.value = String(section.id);
            option.textContent = section.label;
            sectionSelect.appendChild(option);
        });
        if (previous && options.some(function (s) { return String(s.id) === previous; })) {
            sectionSelect.value = previous;
        }
        if (sectionHint) {
            sectionHint.textContent = options.length
                ? "Every year has two sections."
                : "Pick your year level first to see its sections.";
        }
    }

    if (regularBtn && irregularBtn) {
        regularBtn.addEventListener("click", function () { setStudentType(false); });
        irregularBtn.addEventListener("click", function () { setStudentType(true); });
    }

    if (yearLevel) {
        yearLevel.addEventListener("change", function () {
            populateSections();
            if (window.ExamiQSignupFaculty && window.ExamiQSignupFaculty.unlock) {
                window.ExamiQSignupFaculty.unlock();
            }
            syncFaculty();
        });
    }
    if (sectionSelect) {
        sectionSelect.addEventListener("change", function () {
            if (window.ExamiQSignupFaculty && window.ExamiQSignupFaculty.unlock) {
                window.ExamiQSignupFaculty.unlock();
            }
            syncFaculty();
        });
    }

    // Course search + year filter (irregular manual list is hidden after COR).
    var courseSearch = document.getElementById("course-search");
    var coursePicker = document.getElementById("course-picker");
    var courseSearchEmpty = document.getElementById("course-search-empty");
    var courseFilter = document.getElementById("course-filter");
    var courseYear = "";

    function applyCourseFilter() {
        if (!coursePicker) return;
        var q = ((courseSearch && courseSearch.value) || "").trim().toLowerCase();
        var visible = 0;
        coursePicker.querySelectorAll(".course-checkbox").forEach(function (row) {
            var input = row.querySelector(".course-checkbox__input");
            var code = input ? input.getAttribute("data-code") || "" : "";
            var name = input ? input.getAttribute("data-name") || "" : "";
            var year = input ? input.getAttribute("data-year") || "" : "";
            var matchesText = !q || (code + " " + name).toLowerCase().indexOf(q) !== -1;
            var matchesYear = !courseYear || year === courseYear;
            var show = matchesText && matchesYear;
            row.style.display = show ? "" : "none";
            if (show) visible += 1;
        });
        if (courseSearchEmpty) {
            courseSearchEmpty.classList.toggle("hidden", visible > 0);
        }
    }

    if (courseSearch) courseSearch.addEventListener("input", applyCourseFilter);
    if (courseFilter) {
        courseFilter.querySelectorAll("[data-year]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                courseYear = btn.getAttribute("data-year") || "";
                courseFilter.querySelectorAll("[data-year]").forEach(function (other) {
                    other.classList.toggle("is-active", other === btn);
                });
                if (courseSearch) courseSearch.focus();
                applyCourseFilter();
                courseFilter.removeAttribute("open");
            });
        });
    }

    // COR analysis (irregular students).
    var analyzeUrl = document.getElementById("signup-form")
        ? document.getElementById("signup-form").getAttribute("data-cor-analyze-url")
        : "";
    var corAnalyzeBtn = document.getElementById("cor-analyze-btn");
    var corResult = document.getElementById("cor-analyze-result");
    var corZone = document.getElementById("cor-upload-zone");
    var corEmpty = document.getElementById("cor-upload-empty");
    var corFileState = document.getElementById("cor-upload-file");
    var corFileInput = document.getElementById("id_cor_upload");
    var corFileName = document.getElementById("cor-file-name");
    var corFileStatus = document.getElementById("cor-file-status");
    var corFileExt = document.getElementById("cor-file-ext");
    var corFileClear = document.getElementById("cor-file-clear");
    var corSwitchFile = document.getElementById("cor-switch-file");
    var detectedStore = document.getElementById("detected-courses-store");
    var detectedList = document.getElementById("detected-courses-list");
    var analyzed = false;

    function formatSize(bytes) {
        if (!bytes && bytes !== 0) return "";
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1048576) return (bytes / 1024).toFixed(1).replace(/\.0$/, "") + " KB";
        return (bytes / 1048576).toFixed(1).replace(/\.0$/, "") + " MB";
    }

    function showCorEmpty() {
        if (corEmpty) corEmpty.classList.remove("hidden");
        if (corFileState) corFileState.classList.add("hidden");
    }

    function showCorFile(file) {
        if (corEmpty) corEmpty.classList.add("hidden");
        if (corFileState) corFileState.classList.remove("hidden");
        if (corFileName) corFileName.textContent = file.name;
        if (corFileExt) {
            var ext = (file.name.split(".").pop() || "").toUpperCase().slice(0, 4);
            corFileExt.textContent = ext || "FILE";
        }
        if (corFileStatus) {
            var size = formatSize(file.size);
            corFileStatus.textContent =
                (size ? size + " · " : "") + "Ready to analyze";
        }
        if (corResult) corResult.textContent = "";
    }

    function renderDetectedCourses(courses) {
        if (detectedStore) {
            detectedStore.innerHTML = "";
            (courses || []).forEach(function (c) {
                var input = document.createElement("input");
                input.type = "hidden";
                input.name = "courses";
                input.value = String(c.id);
                detectedStore.appendChild(input);
            });
        }
        if (!detectedList) return;
        if (!courses || !courses.length) {
            detectedList.innerHTML =
                '<p class="detected-courses__empty">Upload and analyze your COR first — your courses will appear here.</p>';
            return;
        }
        detectedList.innerHTML = courses
            .map(function (c) {
                var badge =
                    c.confidence && c.confidence !== "high"
                        ? '<span class="detected-courses__badge">check</span>'
                        : "";
                return (
                    '<div class="detected-courses__row">' +
                    '<span class="course-chip">' + escHtml(c.code) + "</span>" +
                    '<span class="detected-courses__name">' + escHtml(c.name || "") + "</span>" +
                    badge +
                    "</div>"
                );
            })
            .join("");
    }

    function resetAnalysis() {
        analyzed = false;
        renderDetectedCourses([]);
        if (window.ExamiQSignupFaculty && window.ExamiQSignupFaculty.unlock) {
            window.ExamiQSignupFaculty.unlock();
        }
    }

    function clearCorFile() {
        if (corFileInput) {
            try {
                corFileInput.value = "";
            } catch (e) { /* ignore */ }
        }
        resetAnalysis();
        showCorEmpty();
    }

    if (corFileInput) {
        corFileInput.classList.add("sr-only");
        corFileInput.addEventListener("change", function () {
            if (corFileInput.files && corFileInput.files.length) {
                resetAnalysis();
                showCorFile(corFileInput.files[0]);
            } else {
                resetAnalysis();
                showCorEmpty();
            }
        });
    }
    if (corZone) {
        ["dragenter", "dragover"].forEach(function (evt) {
            corZone.addEventListener(evt, function (e) {
                e.preventDefault();
                corZone.classList.add("is-dragover");
            });
        });
        ["dragleave", "drop"].forEach(function (evt) {
            corZone.addEventListener(evt, function (e) {
                e.preventDefault();
                corZone.classList.remove("is-dragover");
            });
        });
        corZone.addEventListener("drop", function (e) {
            var files = e.dataTransfer && e.dataTransfer.files;
            if (files && files.length && corFileInput) {
                try {
                    var dt = new DataTransfer();
                    dt.items.add(files[0]);
                    corFileInput.files = dt.files;
                } catch (err) { /* ignore */ }
                showCorFile(files[0]);
                corFileInput.dispatchEvent(new Event("change", { bubbles: true }));
            }
        });
    }
    if (corFileClear) corFileClear.addEventListener("click", clearCorFile);
    if (corSwitchFile) {
        corSwitchFile.addEventListener("click", function () {
            if (corFileInput) corFileInput.click();
        });
    }

    if (corAnalyzeBtn) {
        corAnalyzeBtn.addEventListener("click", function () {
            if (!corFileInput || !corFileInput.files || !corFileInput.files.length) {
                corResult.textContent = "Choose your COR file first.";
                return;
            }
            if (!analyzeUrl) {
                corResult.textContent = "COR analysis is unavailable right now.";
                return;
            }
            corAnalyzeBtn.disabled = true;
            corResult.textContent = "Reading your COR…";
            var fd = new FormData();
            fd.append("cor_file", corFileInput.files[0]);
            var csrfInput = document.querySelector("#signup-form input[name=csrfmiddlewaretoken]");
            fetch(analyzeUrl, {
                method: "POST",
                headers: {
                    Accept: "application/json",
                    "X-CSRFToken": csrfInput ? csrfInput.value : "",
                },
                body: fd,
                credentials: "same-origin",
            })
                .then(function (r) {
                    return r.json().catch(function () {
                        return { error: "Analyzer error." };
                    });
                })
                .then(function (data) {
                    corAnalyzeBtn.disabled = false;
                    if (data.error) {
                        corResult.textContent = data.error;
                        return;
                    }
                    if (data.cor_type === "regular") {
                        corResult.textContent =
                            "This COR shows a regular status. Switch to Regular " +
                            "and pick your year level and section instead.";
                        resetAnalysis();
                        return;
                    }
                    var matched = data.matched || [];
                    if (!matched.length) {
                        corResult.textContent =
                            "We could not confidently match any course codes. " +
                            "Try a clearer photo or PDF of your COR.";
                        return;
                    }
                    analyzed = true;
                    var courses = matched.map(function (m) {
                        return {
                            id: m.subject_id,
                            code: m.code,
                            name: m.name,
                            confidence: m.confidence,
                        };
                    });
                    renderDetectedCourses(courses);
                    if (
                        window.ExamiQSignupFaculty &&
                        window.ExamiQSignupFaculty.setDetectedCourses
                    ) {
                        window.ExamiQSignupFaculty.setDetectedCourses(courses);
                    }
                    if (
                        window.ExamiQSignupFaculty &&
                        window.ExamiQSignupFaculty.lock
                    ) {
                        window.ExamiQSignupFaculty.lock();
                    }
                    var low = 0;
                    matched.forEach(function (m) {
                        if (m.confidence !== "high") low += 1;
                    });
                    corResult.textContent =
                        "Found " + matched.length + " course" +
                        (matched.length > 1 ? "s" : "") +
                        " on your COR — pick a faculty for each below" +
                        (data.unmatched && data.unmatched.length
                            ? " (" + data.unmatched.length + " code(s) did not match)"
                            : "") +
                        (low ? ", " + low + " need a double-check." : ".");
                    var facultyPicker = document.getElementById("faculty-picker-wrapper");
                    if (facultyPicker) facultyPicker.style.display = "";
                })
                .catch(function () {
                    corAnalyzeBtn.disabled = false;
                    corResult.textContent =
                        "The analyzer hit a snag. Try again with a clearer file.";
                });
        });
    }

    var signupForm = document.getElementById("signup-form");
    if (signupForm) {
        signupForm.addEventListener("submit", function (e) {
            if (isIrregular()) {
                if (!corFileInput || !corFileInput.files || !corFileInput.files.length) {
                    e.preventDefault();
                    if (corResult) corResult.textContent = "Attach your COR first.";
                    return false;
                }
                if (!analyzed) {
                    e.preventDefault();
                    if (corResult) {
                        corResult.textContent = "Please click Analyze COR first.";
                    }
                    return false;
                }
            }
        });
    }

    populateSections();
    setStudentType(isIrregular());
})();
