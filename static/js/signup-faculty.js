/**
 * Signup faculty picker: one faculty choice per in-scope subject.
 *
 * Irregular students pick from their checked courses; regular students pick
 * from every curriculum subject of the chosen year level. Options (with
 * teaching load) come from the `faculty-options-data` JSON payload; the
 * picks are synced to the hidden `faculty_selections` input as
 * {"<subject_pk>": "<faculty_pk>"}.
 *
 * Once the course list is displayed, course selection locks: checkboxes,
 * filters and the year-level select are disabled so the confirmed scope
 * cannot be changed mid-flow.
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

    function esc(text) {
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

    document.addEventListener("DOMContentLoaded", function () {
        var optionsBySubject = readJson("faculty-options-data") || {};
        var yearBySubject = readJson("subject-year-map") || {};
        var subjectMetaById = readJson("subject-meta-data") || {};
        var wrapper = document.getElementById("faculty-picker-wrapper");
        var container = document.getElementById("faculty-picker");
        var hiddenInput = document.querySelector('input[name="faculty_selections"]');
        var signupForm = document.getElementById("signup-form");
        if (!wrapper || !container || !hiddenInput) return;

        var irregularInput = document.querySelector(
            '#signup-form input[name="is_irregular"][value="1"]'
        );
        var yearSelect = document.getElementById("id_year_level");
        var coursePicker = document.getElementById("course-picker");
        var filterInputs = [
            document.getElementById("course-search"),
            document.getElementById("course-year"),
            document.getElementById("course-semester"),
        ].filter(Boolean);

        var state = { expanded: null, picks: {}, locked: false, detectedMeta: {} };

        /* The course list and the faculty picker share one panel; hide the
           panel while neither block is visible. */
        function syncSelectionPanel() {
            var panel = document.getElementById("selection-panel");
            if (!panel) return;
            var coursesEl = document.getElementById("irregular-courses-wrapper");
            var coursesVisible = !!coursesEl && coursesEl.style.display !== "none";
            var pickerVisible = wrapper.style.display !== "none";
            panel.style.display = coursesVisible || pickerVisible ? "" : "none";
        }

        // External entry points (COR analyzer bulk set / file reset).
        window.ExamiQSignupFaculty = {
            lock: function () {
                state.locked = true;
                render();
            },
            unlock: function () {
                state.locked = false;
                state.picks = {};
                state.expanded = null;
                state.detectedMeta = {};
                render();
            },
            setDetectedCourses: function (list) {
                state.detectedMeta = {};
                (list || []).forEach(function (c) {
                    state.detectedMeta[String(c.id)] = {
                        code: c.code || "",
                        name: c.name || "",
                    };
                });
            },
        };

        function subjectMeta() {
            var meta = {};
            document.querySelectorAll(".course-checkbox").forEach(function (row) {
                var input = row.querySelector(".course-checkbox__input");
                if (!input) return;
                var nameEl = row.querySelector(".course-checkbox__label");
                meta[String(input.value)] = {
                    code: input.getAttribute("data-code") || "",
                    name:
                        input.getAttribute("data-name") ||
                        (nameEl ? nameEl.textContent.trim() : ""),
                };
            });
            Object.keys(subjectMetaById).forEach(function (pk) {
                var m = subjectMetaById[pk] || {};
                var prev = meta[String(pk)] || {};
                meta[String(pk)] = {
                    code: m.code || prev.code || "",
                    name: m.name || prev.name || "",
                };
            });
            Object.keys(state.detectedMeta).forEach(function (pk) {
                meta[String(pk)] = state.detectedMeta[pk];
            });
            return meta;
        }

        function scopeSubjectIds() {
            var isIrregular = irregularInput && irregularInput.checked;
            if (isIrregular) {
                var ids = [];
                document
                    .querySelectorAll('#detected-courses-store input[name="courses"]')
                    .forEach(function (input) {
                        if (input.value) ids.push(String(input.value));
                    });
                if (!ids.length) {
                    document
                        .querySelectorAll(".course-checkbox__input")
                        .forEach(function (cb) {
                            if (cb.checked) ids.push(String(cb.value));
                        });
                }
                return ids;
            }
            var year = yearSelect ? String(yearSelect.value || "") : "";
            if (!year) return [];
            return Object.keys(yearBySubject).filter(function (pk) {
                return String(yearBySubject[pk]) === year;
            });
        }

        function getOptions(pk) {
            return optionsBySubject[pk] || optionsBySubject[Number(pk)] || [];
        }

        function syncHidden() {
            hiddenInput.value = JSON.stringify(state.picks);
        }

        function lockCourseSelection(on) {
            document.querySelectorAll(".course-checkbox__input").forEach(function (cb) {
                cb.disabled = !!on;
            });
            filterInputs.forEach(function (el) {
                el.disabled = !!on;
            });
            if (yearSelect) yearSelect.disabled = !!on;
            if (coursePicker) {
                coursePicker.classList.toggle("is-locked", !!on);
                coursePicker.style.display = on ? "none" : "";
            }
            var selectedWrap = document.getElementById("selected-courses");
            if (selectedWrap && on) selectedWrap.style.display = "none";
        }

        function slotsText(opt) {
            var cap = opt.capacity || 0;
            var enrolled = opt.enrolled || 0;
            if (cap > 0 && enrolled >= cap) return "Full - " + cap + "/" + cap;
            if (cap > 0) return enrolled + "/" + cap + " slots";
            return enrolled + " student" + (enrolled === 1 ? "" : "s");
        }

        function isFull(opt) {
            var cap = opt.capacity || 0;
            return cap > 0 && (opt.enrolled || 0) >= cap;
        }

        function render() {
            var meta = subjectMeta();
            var ids = scopeSubjectIds();
            container.innerHTML = "";
            var shown = 0;
            var done = 0;

            var isIrregular = irregularInput && irregularInput.checked;
            var head = document.createElement("div");
            head.className = "faculty-picker__head";
            var hint = document.createElement("p");
            hint.className = "faculty-picker__hint";
            var progress = document.createElement("span");
            progress.className = "faculty-picker__progress";
            head.appendChild(hint);
            head.appendChild(progress);
            container.appendChild(head);

            ids.forEach(function (pk) {
                var options = getOptions(pk);
                var code = (meta[pk] && meta[pk].code) || ("Subject " + pk);
                var name = (meta[pk] && meta[pk].name) || "";
                var pickedPk = state.picks[pk] != null ? String(state.picks[pk]) : null;
                var picked = null;
                options.forEach(function (o) {
                    if (String(o.faculty_pk) === pickedPk) picked = o;
                });

                var card = document.createElement("div");
                card.className = "faculty-card";

                if (picked && state.expanded !== pk) {
                    // Confirmed row: green check, code + name, faculty · section, Change.
                    done += 1;
                    shown += 1;
                    card.classList.add("is-done");
                    card.innerHTML =
                        '<span class="faculty-card__check" aria-hidden="true">' +
                        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>' +
                        "</span>" +
                        '<span class="faculty-card__body">' +
                        '<span class="faculty-card__title">' +
                        esc(code) +
                        (name ? " " + esc(name) : "") +
                        "</span>" +
                        '<span class="faculty-card__sub">' +
                        esc(picked.name) +
                        (picked.section_label ? " &middot; " + esc(picked.section_label) : "") +
                        "</span>" +
                        "</span>" +
                        '<button type="button" class="faculty-card__action" data-change="' +
                        esc(pk) +
                        '">Change</button>';
                } else if (!options.length) {
                    // No faculty available yet: disabled row.
                    shown += 1;
                    card.classList.add("is-empty");
                    card.innerHTML =
                        '<span class="faculty-card__radio" aria-hidden="true"></span>' +
                        '<span class="faculty-card__body">' +
                        '<span class="faculty-card__title">' +
                        esc(code) +
                        (name ? " " + esc(name) : "") +
                        "</span>" +
                        '<span class="faculty-card__sub">No faculty yet available</span>' +
                        "</span>" +
                        '<button type="button" class="faculty-card__action" disabled>Choose</button>';
                } else if (state.expanded === pk) {
                    // Expanded selector row.
                    shown += 1;
                    var section = options[0].section_label || "";
                    var optsHtml = options
                        .map(function (opt) {
                            var full = isFull(opt);
                            var oid = "faculty-" + pk + "-" + opt.faculty_pk;
                            return (
                                '<label class="faculty-card__option' +
                                (full ? " is-full" : "") +
                                '" for="' +
                                esc(oid) +
                                '">' +
                                '<input type="radio" class="faculty-card__radio-input" id="' +
                                esc(oid) +
                                '" name="faculty_for_' +
                                esc(pk) +
                                '" value="' +
                                esc(String(opt.faculty_pk)) +
                                '" data-subject="' +
                                esc(pk) +
                                '"' +
                                (String(opt.faculty_pk) === pickedPk ? " checked" : "") +
                                (full ? " disabled" : "") +
                                ">" +
                                '<span class="faculty-card__radio" aria-hidden="true"></span>' +
                                '<span class="faculty-card__option-main">' +
                                '<span class="faculty-card__option-name">' +
                                esc(opt.name) +
                                "</span>" +
                                (opt.section_label
                                    ? '<span class="faculty-card__option-sec">' +
                                      esc(opt.section_label) +
                                      "</span>"
                                    : "") +
                                "</span>" +
                                '<span class="faculty-card__slots">' +
                                esc(slotsText(opt)) +
                                "</span>" +
                                "</label>"
                            );
                        })
                        .join("");
                    card.classList.add("is-open");
                    card.innerHTML =
                        '<span class="faculty-card__radio" aria-hidden="true"></span>' +
                        '<span class="faculty-card__body">' +
                        '<span class="faculty-card__title">' +
                        esc(code) +
                        (name ? " " + esc(name) : "") +
                        '<span class="faculty-card__sec">' +
                        esc(section) +
                        "</span></span>" +
                        '<span class="faculty-card__select-label">Select a faculty</span>' +
                        '<span class="faculty-card__options">' +
                        optsHtml +
                        "</span>" +
                        "</span>";
                } else {
                    // Collapsed unpicked row.
                    shown += 1;
                    var sec = options[0].section_label || "";
                    card.innerHTML =
                        '<span class="faculty-card__radio" aria-hidden="true"></span>' +
                        '<span class="faculty-card__body">' +
                        '<span class="faculty-card__title">' +
                        esc(code) +
                        (name ? " " + esc(name) : "") +
                        "</span>" +
                        (sec
                            ? '<span class="faculty-card__sub">' + esc(sec) + "</span>"
                            : "") +
                        "</span>" +
                        '<button type="button" class="faculty-card__action" data-choose="' +
                        esc(pk) +
                        '">Choose</button>';
                }
                container.appendChild(card);
            });

            if (isIrregular) {
                hint.textContent =
                    "We found " +
                    ids.length +
                    " course" +
                    (ids.length === 1 ? "" : "s") +
                    " on your COR. Pick one faculty for each course to continue.";
            } else {
                hint.textContent =
                    "Your year level includes " +
                    ids.length +
                    " course" +
                    (ids.length === 1 ? "" : "s") +
                    ". Pick one faculty for each course to continue.";
            }
            progress.textContent = done + " of " + ids.length + " done";

            container.querySelectorAll("[data-choose]").forEach(function (btn) {
                btn.addEventListener("click", function () {
                    state.expanded = btn.getAttribute("data-choose");
                    render();
                });
            });
            container.querySelectorAll("[data-change]").forEach(function (btn) {
                btn.addEventListener("click", function () {
                    state.expanded = btn.getAttribute("data-change");
                    render();
                });
            });
            container
                .querySelectorAll('input[type="radio"][data-subject]')
                .forEach(function (radio) {
                    radio.addEventListener("change", function () {
                        state.picks[radio.getAttribute("data-subject")] = radio.value;
                        state.expanded = null;
                        syncHidden();
                        render();
                    });
                });

            // Confirm bar.
            var bar = document.createElement("div");
            bar.className = "faculty-picker__confirm";
            bar.innerHTML =
                '<span class="faculty-picker__confirm-main">Confirm courses (' +
                done +
                " of " +
                ids.length +
                ")</span>" +
                '<span class="faculty-picker__confirm-sub">' +
                (done >= ids.length && ids.length
                    ? "All set — create your account below."
                    : "Choose a faculty for every course to continue.") +
                "</span>";
            container.appendChild(bar);

            wrapper.style.display = shown ? "" : "none";
            // Once the course list is displayed in bulk (COR analysis tick or
            // year-level select) it locks: no add/remove afterwards. Manual
            // checkbox ticks keep the scope editable until then.
            lockCourseSelection(state.locked && shown > 0);
            syncHidden();
            syncSelectionPanel();
        }

        document.querySelectorAll(".course-checkbox__input").forEach(function (cb) {
            cb.addEventListener("change", function () {
                state.expanded = null;
                render();
            });
        });
        if (yearSelect) {
            yearSelect.addEventListener("change", function () {
                state.picks = {};
                state.expanded = null;
                state.locked = true;
                render();
            });
        }
        document.querySelectorAll(".student-type-switch__btn").forEach(function (btn) {
            btn.addEventListener("click", function () {
                state.picks = {};
                state.expanded = null;
                state.locked = false;
                window.setTimeout(render, 0);
            });
        });

        render();

        if (signupForm) {
            signupForm.addEventListener("submit", function (e) {
                var ids = scopeSubjectIds();
                var missing = ids.filter(function (pk) {
                    var options = getOptions(pk);
                    if (!options.length) return false;
                    return !state.picks[pk];
                });
                if (missing.length) {
                    e.preventDefault();
                    wrapper.style.display = "";
                    wrapper.scrollIntoView({ behavior: "smooth", block: "center" });
                    return false;
                }
                syncHidden();
            });
        }
    });
})();
