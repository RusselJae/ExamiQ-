/**
 * Shared behaviour for the question editors (single question + batch draft).
 *
 * Drives the answer-choice circles, the two student-view modes, the
 * "Ready to publish" checklist, the unsaved-changes badge, and the inner
 * Explanation / Solution steps tabs. Field wiring is declared with data-*
 * attributes on the form so one implementation serves both screens.
 */
(function () {
    "use strict";

    function qs(root, selector) {
        if (!root || !selector) return null;
        return root.querySelector(selector);
    }

    function qsa(root, selector) {
        if (!root || !selector) return [];
        return Array.prototype.slice.call(root.querySelectorAll(selector));
    }

    function textOf(el) {
        return el ? String(el.value || "").trim() : "";
    }

    // NOTE: the editor form carries the data-*-selector wiring itself.
    // An earlier revision resolved `root` to the page header (a sibling of the
    // form), so every selector fell back to defaults, empty selectors threw,
    // and the whole editor (tabs + student preview) never booted.
    function Editor(form) {
        this.root = form;
        this.form = form;
        this.stemSel = form.getAttribute("data-stem-selector") || "#id_stem";
        this.choiceSel = form.getAttribute("data-choice-selector") || "";
        this.correctSel = form.getAttribute("data-correct-selector") || "";
        this.explainSel = form.getAttribute("data-explanation-selector") || "";
        this.stepSel = form.getAttribute("data-steps-selector") || "";
        this.preview = qs(form, "[data-student-preview]");
        this.badge = document.querySelector("[data-unsaved-badge]");
        this.baseline = this.serialize();
    }

    Editor.prototype.serialize = function () {
        return JSON.stringify({
            stem: textOf(qs(this.form, this.stemSel)),
            choices: qsa(this.form, this.choiceSel).map(function (el) {
                return el.value || "";
            }),
            correct: this.correctValue(),
            explain: qsa(this.form, this.explainSel).map(function (el) {
                return el.value || "";
            }),
            steps: qsa(this.form, this.stepSel).map(function (el) {
                return el.value || "";
            }),
        });
    };

    Editor.prototype.correctValue = function () {
        if (!this.correctSel) return "";
        var checked = qs(this.form, this.correctSel + ":checked");
        return checked ? checked.value || "" : "";
    };

    Editor.prototype.choices = function () {
        return qsa(this.form, this.choiceSel);
    };

    /* ---------------- answer choice circles ---------------- */
    Editor.prototype.bindChoices = function () {
        var self = this;
        if (!self.correctSel) return;
        qsa(this.form, "[data-choice-card]").forEach(function (card) {
            var circle = qs(card, "[data-choice-radio]");
            if (!circle) return;
            circle.addEventListener("click", function (event) {
                event.preventDefault();
                // Pick exactly one correct answer across every card.
                qsa(self.form, self.correctSel).forEach(function (input) {
                    input.checked = false;
                });
                // The correct-input lives inside its own card, so scope the
                // lookup there instead of parsing the selector for a name.
                var target = qs(card, self.correctSel);
                if (target) {
                    target.checked = true;
                    target.dispatchEvent(new Event("change", { bubbles: true }));
                }
                self.refresh();
            });
        });
    };

    /* ---------------- student preview ---------------- */
    Editor.prototype.renderPreview = function () {
        if (!this.preview) return;
        var stem = textOf(qs(this.form, this.stemSel));
        var correct = this.correctValue();
        var mode = qs(this.root, '[data-student-mode-btn].is-active');
        var wrong = mode && mode.getAttribute("data-student-mode-btn") === "wrong";

        var html = "";
        if (wrong) {
            var parts = qsa(this.form, this.explainSel)
                .map(function (el) {
                    return textOf(el);
                })
                .filter(Boolean);
            html = parts.length
                ? parts
                      .map(function (text) {
                          return '<p class="qe-student__line">' + escapeHtml(text) + "</p>";
                      })
                      .join("")
                : '<p class="qe-student__line qe-student__line--empty">' +
                  "Add an explanation to show students here." +
                  "</p>";
        } else {
            html =
                '<p class="qe-student__stem' +
                (stem ? "" : " is-placeholder") +
                '">' +
                escapeHtml(stem || "Your question will appear here.") +
                "</p>" +
                '<ul class="qe-student__options">' +
                this.choices()
                    .map(function (input) {
                        var letter = input.getAttribute("data-choice-label") || "";
                        var text = textOf(input);
                        var isCorrect = letter && letter === correct;
                        return (
                            '<li class="qe-student__option' +
                            (isCorrect ? " is-correct" : "") +
                            (text ? "" : " is-empty") +
                            '">' +
                            '<span class="qe-student__option-text">' +
                            escapeHtml(text || "Choice " + letter) +
                            "</span>" +
                            (isCorrect
                                ? '<span class="qe-student__flag">Correct</span>'
                                : "") +
                            "</li>"
                        );
                    })
                    .join("") +
                "</ul>";
        }
        this.preview.innerHTML = html;
    };

    /* ---------------- readiness checklist ---------------- */
    Editor.prototype.refreshChecks = function () {
        var stem = textOf(qs(this.form, this.stemSel));
        var choices = this.choices();
        var filledChoices = choices.filter(function (el) {
            return textOf(el);
        });
        var hasCorrect = !!this.correctValue();
        var explain = qsa(this.form, this.explainSel)
            .map(function (el) {
                return textOf(el);
            })
            .filter(Boolean);
        var steps = qsa(this.form, this.stepSel)
            .map(function (el) {
                return textOf(el);
            })
            .filter(Boolean);

        var state = {
            question: !!stem,
            choices: choices.length > 0 && filledChoices.length === choices.length && hasCorrect,
            explanation: explain.length > 0,
            steps: steps.length > 0,
        };
        var counts = {
            choices: filledChoices.length,
            steps: steps.length,
        };

        qsa(this.root, "[data-ready-check]").forEach(function (item) {
            var key = item.getAttribute("data-ready-check");
            var label = qs(item, ".qe-ready__label");
            var done = !!state[key];
            item.classList.toggle("is-done", done);
            var suffix = counts[key];
            if (label) {
                if (key === "choices") {
                    label.textContent = suffix + " Choices";
                } else if (key === "steps") {
                    label.textContent = suffix + (suffix === 1 ? " Step" : " Steps");
                } else {
                    label.textContent = key.charAt(0).toUpperCase() + key.slice(1);
                }
            }
        });
    };

    /* ---------------- tabs + dirty state ---------------- */
    Editor.prototype.bindTabs = function () {
        var root = this.root;
        qsa(root, "[data-subtab]").forEach(function (tab) {
            tab.addEventListener("click", function () {
                var target = tab.getAttribute("data-subtab");
                qsa(root, "[data-subtab]").forEach(function (other) {
                    var on = other === tab;
                    other.classList.toggle("is-active", on);
                    other.setAttribute("aria-selected", on ? "true" : "false");
                });
                qsa(root, "[data-subpanel]").forEach(function (panel) {
                    var on = panel.getAttribute("data-subpanel") === target;
                    panel.classList.toggle("hidden", !on);
                });
            });
        });
    };

    Editor.prototype.bindModes = function () {
        var self = this;
        qsa(this.root, "[data-student-mode-btn]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                qsa(self.root, "[data-student-mode-btn]").forEach(function (other) {
                    other.classList.toggle("is-active", other === btn);
                });
                self.renderPreview();
            });
        });
    };

    Editor.prototype.refreshDirty = function () {
        var dirty = this.serialize() !== this.baseline;
        if (this.badge) this.badge.hidden = !dirty;
        this.root.classList.toggle("is-dirty", dirty);
    };

    Editor.prototype.refresh = function () {
        this.renderPreview();
        this.refreshChecks();
        this.refreshDirty();
    };

    Editor.prototype.bindCancel = function () {
        var self = this;
        qsa(this.root, "[data-editor-cancel]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                if (self.serialize() === self.baseline) {
                    goBack(btn);
                    return;
                }
                var ok = window.confirm(
                    "Discard your unsaved changes and leave this screen?"
                );
                if (ok) goBack(btn);
            });
        });
    };

    function escapeHtml(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function goBack(btn) {
        var fallback = btn && btn.getAttribute("data-cancel-url");
        // Prefer real history so we land on whatever screen the user came
        // from (question list, batch draft, analytics, ...).
        if (window.history.length > 1) {
            window.history.back();
            return;
        }
        if (fallback) {
            window.location.href = fallback;
            return;
        }
        window.location.reload();
    }

    function boot() {
        var form = document.querySelector("form[data-question-editor]");
        if (!form) return;
        var editor = new Editor(form);
        window.ExamiQQuestionEditor = editor;
        editor.bindChoices();
        editor.bindTabs();
        editor.bindModes();
        editor.bindCancel();

        // Any input inside the form repaints the preview and checklist.
        form.addEventListener("input", function () {
            editor.refresh();
        });
        form.addEventListener("change", function () {
            editor.refresh();
        });
        editor.refresh();

        window.addEventListener("beforeunload", function (event) {
            if (editor.serialize() === editor.baseline) return;
            event.preventDefault();
            event.returnValue = "";
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();