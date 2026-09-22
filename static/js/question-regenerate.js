/**
 * Regenerate a high-mistake question from the faculty edit screen.
 * Polls the shared AI generate status endpoint and applies one variation to the form.
 */
(function () {
    "use strict";

    function getCookie(name) {
        var match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
        return match ? decodeURIComponent(match[2]) : "";
    }

    function choiceInputs() {
        return Array.prototype.slice.call(
            document.querySelectorAll("#mcq-choices-card input[name$='-text']")
        );
    }

    function correctInputs() {
        return Array.prototype.slice.call(
            document.querySelectorAll("#mcq-choices-card input[name$='-is_correct']")
        );
    }

    function applyAdaptive(variation) {
        var keys = [
            "what_went_wrong",
            "why",
            "quick_check",
            "remember",
            "worked_example",
        ];
        keys.forEach(function (key) {
            var el = document.getElementById("id_adaptive_" + key);
            if (!el) return;
            var value = variation[key];
            if (value == null && variation.adaptive_explanation) {
                value = variation.adaptive_explanation[key];
            }
            if (value != null) el.value = String(value);
        });
    }

    function applySteps(variation) {
        var steps = variation.explanation_steps || variation.steps || [];
        if (!Array.isArray(steps)) steps = [];
        steps = steps
            .map(function (step) {
                return String(step || "").trim();
            })
            .filter(Boolean);

        var contents = Array.prototype.slice.call(
            document.querySelectorAll('textarea[name^="steps-"][name$="-content"]')
        );
        var orders = Array.prototype.slice.call(
            document.querySelectorAll('input[name^="steps-"][name$="-order"]')
        );
        var deletes = Array.prototype.slice.call(
            document.querySelectorAll('input[name^="steps-"][name$="-DELETE"]')
        );

        for (var i = 0; i < contents.length; i++) {
            if (i < steps.length) {
                contents[i].value = steps[i];
                if (orders[i]) orders[i].value = String(i + 1);
                if (deletes[i]) deletes[i].checked = false;
            } else {
                contents[i].value = "";
                if (deletes[i]) deletes[i].checked = true;
            }
        }
    }

    function applyVariation(variation) {
        var stem = document.getElementById("id_stem");
        var concept = document.getElementById("id_concept_tag");
        if (stem && variation.stem) stem.value = variation.stem;
        if (concept && variation.concept_tag != null) {
            concept.value = variation.concept_tag || "";
        }

        var labels = ["A", "B", "C", "D"];
        var byLabel = {};
        (variation.choices || []).forEach(function (choice) {
            byLabel[(choice.label || "").toUpperCase()] = choice;
        });
        var texts = choiceInputs();
        var corrects = correctInputs();
        labels.forEach(function (label, index) {
            var choice = byLabel[label];
            if (!choice) return;
            if (texts[index]) texts[index].value = choice.text || "";
            if (corrects[index]) {
                corrects[index].checked = !!choice.is_correct ||
                    (variation.correct_label || "").toUpperCase() === label;
            }
        });

        applyAdaptive(variation);
        applySteps(variation);
    }

    function closeModal() {
        var root = document.getElementById("question-regenerate-modal-root");
        if (root) root.innerHTML = "";
    }

    function renderModal(payload) {
        var root = document.getElementById("question-regenerate-modal-root");
        if (!root) return;
        var variations = payload.variations || [];
        var error = payload.error;
        var html = [
            '<div class="modal-overlay fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" id="regenerate-modal">',
            '  <div class="bento-card bento-card--elevated p-6 max-w-3xl w-full mx-4 max-h-[85vh] overflow-y-auto shadow-xl" role="dialog" aria-modal="true">',
            '    <div class="flex justify-between items-start mb-4">',
            '      <div>',
            '        <h2 class="text-lg font-semibold text-examiq-navy">Regenerated questions</h2>',
            '        <p class="text-sm text-examiq-slate mt-1">Pick one clearer variation at the same difficulty, then review before saving.</p>',
            "      </div>",
            '      <button type="button" data-close-regenerate class="text-examiq-slate hover:text-examiq-navy text-2xl leading-none p-1" aria-label="Close">&times;</button>',
            "    </div>",
        ];
        if (error) {
            html.push(
                '<div class="bg-amber-50 border border-amber-200 text-amber-900 text-sm px-4 py-3 mb-4">' +
                    error +
                    "</div>"
            );
        } else if (!variations.length) {
            html.push('<p class="text-examiq-slate mb-4">No variations generated. Try again.</p>');
        } else {
            html.push('<div class="space-y-3 mb-6">');
            variations.forEach(function (variation, index) {
                html.push(
                    '<label class="block border border-slate-200 p-4 bg-white cursor-pointer">',
                    '  <span class="flex items-start gap-3">',
                    '    <input type="radio" name="regenerate_pick" value="' +
                        index +
                        '"' +
                        (index === 0 ? " checked" : "") +
                        ' class="mt-1">',
                    '    <span class="flex-1 min-w-0">',
                    '      <span class="text-examiq-navy font-medium block"></span>',
                    "    </span>",
                    "  </span>",
                    "</label>"
                );
            });
            html.push("</div>");
            html.push(
                '<div class="flex flex-wrap gap-3">',
                '  <button type="button" class="btn-primary" data-apply-regenerate>Apply to form</button>',
                '  <button type="button" class="btn-secondary" data-close-regenerate>Cancel</button>',
                "</div>"
            );
        }
        if (!variations.length || error) {
            html.push(
                '<button type="button" class="btn-secondary" data-close-regenerate>Close</button>'
            );
        }
        html.push("</div></div>");
        root.innerHTML = html.join("");

        var labels = root.querySelectorAll(".text-examiq-navy.font-medium.block");
        variations.forEach(function (variation, index) {
            if (!labels[index]) return;
            labels[index].textContent = variation.stem || "Variation " + (index + 1);
            if (variation.choices && variation.choices.length) {
                var list = document.createElement("ul");
                list.className = "text-sm text-examiq-slate mt-2 space-y-1";
                variation.choices.forEach(function (choice) {
                    var li = document.createElement("li");
                    li.textContent =
                        (choice.label || "") +
                        ". " +
                        (choice.text || "") +
                        (choice.is_correct ? " ✓" : "");
                    list.appendChild(li);
                });
                labels[index].parentNode.appendChild(list);
            }
        });

        root.querySelectorAll("[data-close-regenerate]").forEach(function (btn) {
            btn.addEventListener("click", closeModal);
        });
        var applyBtn = root.querySelector("[data-apply-regenerate]");
        if (applyBtn) {
            applyBtn.addEventListener("click", function () {
                var selected = root.querySelector('input[name="regenerate_pick"]:checked');
                var index = selected ? parseInt(selected.value, 10) : 0;
                var variation = variations[index];
                if (variation) applyVariation(variation);
                closeModal();
            });
        }
        window.__regenerateVariations = variations;
    }

    function setBusy(btn, busy) {
        if (!btn) return;
        btn.disabled = !!busy;
        btn.textContent = busy ? "Regenerating…" : "Regenerate question";
    }

    function pollStatus(url, btn) {
        return fetch(url, {
            headers: { Accept: "application/json" },
            credentials: "same-origin",
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    if (!response.ok) {
                        throw new Error(data.error || "Could not check generation status.");
                    }
                    return data;
                });
            })
            .then(function (data) {
                if (!data.done) {
                    return new Promise(function (resolve) {
                        setTimeout(function () {
                            resolve(pollStatus(url, btn));
                        }, 1200);
                    });
                }
                renderModal(data);
                setBusy(btn, false);
            });
    }

    function start() {
        var btn = document.getElementById("question-regenerate-btn");
        if (!btn) return;
        btn.addEventListener("click", function () {
            var url = btn.getAttribute("data-regenerate-url");
            if (!url) return;
            setBusy(btn, true);
            var csrf =
                btn.getAttribute("data-csrf") ||
                getCookie("csrftoken") ||
                (document.querySelector("[name=csrfmiddlewaretoken]") || {}).value ||
                "";
            fetch(url, {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrf,
                    Accept: "application/json",
                },
                credentials: "same-origin",
            })
                .then(function (response) {
                    return response.json().then(function (data) {
                        if (!response.ok) {
                            throw new Error(data.error || "Regenerate failed.");
                        }
                        return data;
                    });
                })
                .then(function (data) {
                    if (!data.status_url) {
                        throw new Error("Missing status URL.");
                    }
                    return pollStatus(data.status_url, btn);
                })
                .catch(function (err) {
                    setBusy(btn, false);
                    renderModal({ error: err.message || "Regenerate failed.", variations: [] });
                });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})();
