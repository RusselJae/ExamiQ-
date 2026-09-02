/**
 * Visual tutor response renderer — step cards, progressive reveal, optional chart.
 */
(function () {
    "use strict";

    function escapeHtml(text) {
        var div = document.createElement("div");
        div.textContent = text || "";
        return div.innerHTML;
    }

    function katexRender(el) {
        if (typeof window.renderMathInElement !== "undefined" && el) {
            window.renderMathInElement(el, {
                delimiters: [
                    { left: "$$", right: "$$", display: true },
                    { left: "$", right: "$", display: false },
                ],
            });
        }
    }

    function parseStructured(raw) {
        if (!raw) return null;
        if (typeof raw === "object") return raw;
        var text = String(raw).trim();
        if (!text) return null;
        if (text.charAt(0) === "`") {
            text = text.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
        }
        try {
            return JSON.parse(text);
        } catch (e) {
            var match = text.match(/\{[\s\S]*\}/);
            if (!match) return null;
            try {
                return JSON.parse(match[0]);
            } catch (err) {
                return null;
            }
        }
    }

    function extractFeedbackText(raw) {
        var text = String(raw || "").trim();
        if (!text) return "";
        if (text.charAt(0) === "`") {
            text = text.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim();
        }
        var candidates = [text];
        var match = text.match(/\{[\s\S]*\}/);
        if (match) candidates.push(match[0]);
        for (var i = 0; i < candidates.length; i += 1) {
            try {
                var data = JSON.parse(candidates[i]);
                if (data && typeof data === "object") {
                    if (data.feedback) return String(data.feedback).trim();
                    if (data.why_wrong) return String(data.why_wrong).trim();
                    if (data.message) return String(data.message).trim();
                    if (data.text) return String(data.text).trim();
                }
            } catch (err) {
                /* try next candidate */
            }
        }
        return text;
    }

    function normalizeSteps(data) {
        if (!data) return [];
        if (Array.isArray(data.steps) && data.steps.length) {
            return data.steps.map(function (step, index) {
                if (typeof step === "string") {
                    return {
                        title: "Step " + (index + 1),
                        operation: "",
                        equations: [step],
                        highlight: "",
                    };
                }
                return {
                    title: step.title || "Step " + (index + 1),
                    operation: step.operation || "",
                    equations: Array.isArray(step.equations)
                        ? step.equations
                        : step.equation
                          ? [step.equation]
                          : [],
                    highlight: step.highlight || "",
                };
            });
        }
        return [];
    }

    function wrapBareLatex(text) {
        var t = String(text || "").trim();
        if (!t || /\$/.test(t)) return t;
        if (/\\frac|\\sqrt|\\sum|\\int|\\lim|\\text\{|\\rightarrow|\^\{|_\{/.test(t)) {
            return "$" + t + "$";
        }
        return t;
    }

    function looksLikeMathLine(text) {
        var t = String(text || "").trim();
        if (!t) return false;
        if (/^\$/.test(t) || /\$\$/.test(t)) return true;
        if (/\\frac|\\sqrt|\\sum|\\int|\\xrightarrow|\\text\{/.test(t)) return true;
        var words = t.split(/\s+/);
        if (words.length > 18) return false;
        if (/[=+\-×÷^√≤≥≠≈]/.test(t) && /[0-9a-zA-Z]/.test(t)) return true;
        if (/[0-9]/.test(t) && /[=+\-]/.test(t) && !/[.!?]{2,}/.test(t)) return true;
        return false;
    }

    function shortTitle(text, fallback) {
        var t = String(text || "").trim();
        if (!t) return fallback;
        if (t.length <= 42) return t;
        var cut = t.slice(0, 40);
        var lastSpace = cut.lastIndexOf(" ");
        if (lastSpace > 16) cut = cut.slice(0, lastSpace);
        return cut.trim() + "…";
    }

    function stepsFromCorrectionList(list) {
        if (!list || !list.length) return [];
        var steps = [];
        var current = null;

        function flush() {
            if (!current) return;
            if (
                !current.operation &&
                !current.equations.length &&
                !current.title
            ) {
                current = null;
                return;
            }
            steps.push(current);
            current = null;
        }

        function ensureStep() {
            if (!current) {
                current = {
                    title: "Step " + (steps.length + 1),
                    operation: "",
                    equations: [],
                    highlight: "",
                };
            }
        }

        list.forEach(function (item) {
            var text = typeof item === "string" ? item : String(item || "");
            var lines = text
                .split(/\n+/)
                .map(function (line) {
                    return line.trim();
                })
                .filter(Boolean);

            lines.forEach(function (line) {
                var numbered = line.match(/^Step\s*\d+\s*[:.-]\s*(.*)$/i);
                if (numbered) {
                    flush();
                    var rest = (numbered[1] || "").trim();
                    current = {
                        title: "Step " + (steps.length + 1),
                        operation: looksLikeMathLine(rest) ? "" : rest,
                        equations: looksLikeMathLine(rest) ? [rest] : [],
                        highlight: "",
                    };
                    if (current.operation && !looksLikeMathLine(current.operation)) {
                        current.title = shortTitle(
                            current.operation,
                            current.title
                        );
                        if (current.title === current.operation) {
                            current.operation = "";
                        }
                    }
                    return;
                }

                if (looksLikeMathLine(line)) {
                    ensureStep();
                    current.equations.push(line);
                    return;
                }

                var colon = line.indexOf(":");
                flush();
                if (colon > 0 && colon < 40) {
                    current = {
                        title: line.slice(0, colon).trim(),
                        operation: line.slice(colon + 1).trim(),
                        equations: [],
                        highlight: "",
                    };
                    return;
                }

                current = {
                    title: shortTitle(line, "Step " + (steps.length + 1)),
                    operation: line.length > 42 ? line : "",
                    equations: [],
                    highlight: "",
                };
                if (!current.operation && current.title !== line) {
                    current.operation = line;
                }
            });
        });

        flush();

        return steps.map(function (step, index) {
            if (/^Step\s+\d+$/i.test(step.title) && step.operation) {
                step.title = shortTitle(step.operation, "Step " + (index + 1));
                if (step.title === step.operation) {
                    step.operation = "";
                }
            } else if (/^Step\s+\d+$/i.test(step.title)) {
                step.title = "Step " + (index + 1);
            }
            return step;
        });
    }

    function renderChart(container, chart) {
        if (!chart || !container || typeof Chart === "undefined") return;
        if (!chart.points || !chart.points.length) return;
        var wrap = document.createElement("div");
        wrap.className = "tutor-visual-chart";
        if (chart.title) {
            var title = document.createElement("p");
            title.className = "tutor-visual-chart__title";
            title.textContent = chart.title;
            wrap.appendChild(title);
        }
        var canvas = document.createElement("canvas");
        canvas.height = 160;
        wrap.appendChild(canvas);
        container.appendChild(wrap);

        var labels = chart.points.map(function (p) {
            return String(p[0]);
        });
        var values = chart.points.map(function (p) {
            return Number(p[1]);
        });
        var annotations = (chart.markers || []).map(function (m) {
            return m.label || "";
        });

        new Chart(canvas, {
            type: "line",
            data: {
                labels: labels,
                datasets: [
                    {
                        data: values,
                        borderColor: "#2563eb",
                        backgroundColor: "#2563eb22",
                        fill: true,
                        tension: 0.35,
                        pointRadius: 3,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            afterLabel: function (ctx) {
                                return annotations[ctx.dataIndex] || "";
                            },
                        },
                    },
                },
                scales: {
                    x: { grid: { display: false } },
                    y: { beginAtZero: true, grid: { color: "#f1f5f9" } },
                },
            },
        });
    }

    function stripLatexDecorations(text) {
        return stripInternalMetaContent(
            String(text || "")
                .replace(/\\text\{([^}]*)\}/g, "$1")
                .replace(/\\'/g, "'")
                .replace(/\{\s*'([^']*)'\s*\}/g, "'$1'")
                .trim()
        );
    }

    function prepareMathField(text, mode) {
        var t = String(text || "").trim();
        if (!t) return "";
        if (mode === "label") {
            return escapeHtml(stripLatexDecorations(t));
        }
        t = wrapBareLatex(t);
        if (/\\[a-zA-Z]/.test(t) && !/\$/.test(t)) {
            t = "$" + t + "$";
        }
        return escapeHtml(t);
    }

    var INTERNAL_META_LABELS =
        /^(query|focus|redirect|instruction|note|context|metadata|system|response type)$/i;

    function isInternalMetaLabel(text) {
        return INTERNAL_META_LABELS.test(String(text || "").trim());
    }

    function stripInternalMetaContent(text) {
        return String(text || "")
            .split(/\n+/)
            .map(function (line) {
                var trimmed = line.trim();
                if (!trimmed) return "";
                var match = trimmed.match(/^([A-Za-z][A-Za-z\s]{0,24}):\s*(.*)$/);
                if (match && isInternalMetaLabel(match[1])) {
                    return match[2].trim();
                }
                return trimmed;
            })
            .filter(Boolean)
            .join("\n")
            .trim();
    }

    function scrubInternalMetaSteps(steps) {
        var cleaned = [];
        (steps || []).forEach(function (step) {
            if (isInternalMetaLabel(step.title)) {
                var text = stripInternalMetaContent(step.operation || "");
                (step.equations || []).forEach(function (eq) {
                    var line = stripInternalMetaContent(eq);
                    if (line) {
                        text = text ? text + "\n" + line : line;
                    }
                });
                if (text) {
                    cleaned.push({
                        title: "Step " + (cleaned.length + 1),
                        operation: text,
                        equations: [],
                        highlight: "",
                    });
                }
                return;
            }
            cleaned.push({
                title: step.title,
                operation: stripInternalMetaContent(step.operation || ""),
                equations: (step.equations || []).map(stripInternalMetaContent).filter(Boolean),
                highlight: step.highlight || "",
            });
        });
        return cleaned;
    }

    function plainTutorText(structured, raw) {
        if (structured && structured.type === "text" && structured.content) {
            return stripLatexDecorations(structured.content);
        }
        var parts = [];
        if (structured) {
            if (structured.feedback) parts.push(structured.feedback);
            if (structured.message) parts.push(structured.message);
            if (structured.why) parts.push(structured.why);
            var steps = normalizeSteps(structured);
            steps.forEach(function (step) {
                if (step.title && !/^Step\s+\d+$/i.test(step.title)) {
                    parts.push(step.title);
                }
                if (step.operation) parts.push(step.operation);
                (step.equations || []).forEach(function (eq) {
                    parts.push(eq);
                });
            });
            if (structured.answer) parts.push(structured.answer);
        }
        var combined = parts.filter(Boolean).join("\n\n");
        return stripLatexDecorations(extractFeedbackText(combined || raw || ""));
    }

    function looksLikePlainMathSolution(raw) {
        var text = String(raw || "").trim();
        if (!text) return false;
        var lines = text.split(/\n+/).map(function (line) {
            return line.trim();
        }).filter(Boolean);
        if (lines.length < 2) return false;
        var numbered = lines.filter(function (line) {
            return /^(?:step\s*)?\d+[.)]\s+/i.test(line);
        });
        if (numbered.length < 2) return false;
        return lines.some(looksLikeMathLine);
    }

    function isSolutionResponse(structured, raw) {
        var data = structured || parseStructured(raw);
        if (!data) {
            return looksLikePlainMathSolution(raw);
        }
        if (data.type === "text") {
            return false;
        }
        if (data.type === "solution") {
            return true;
        }
        return !!(data.steps && data.steps.length);
    }

    function isRichTutorResponse(structured, raw) {
        return isSolutionResponse(structured, raw);
    }

    function renderVisualResponse(host, options) {
        options = options || {};
        if (!host) return null;

        var structured = options.structured || parseStructured(options.raw);
        var useStructured =
            structured &&
            structured.type !== "text" &&
            (structured.type === "solution" || (structured.steps && structured.steps.length));
        var steps = useStructured
            ? scrubInternalMetaSteps(normalizeSteps(structured))
            : [];
        if (!steps.length && options.correctionSteps) {
            steps = stepsFromCorrectionList(options.correctionSteps);
        }
        if (!steps.length && looksLikePlainMathSolution(options.raw)) {
            steps = stepsFromCorrectionList(
                String(options.raw || "")
                    .split(/\n+/)
                    .map(function (line) {
                        return line.trim();
                    })
                    .filter(Boolean)
            );
        }
        var answer =
            (useStructured && structured && structured.answer) ||
            options.finalAnswer ||
            "";
        var why = stripLatexDecorations(extractFeedbackText(options.why || ""));
        var progressive = options.progressive !== false;
        var revealed = progressive ? 0 : steps.length;

        host.innerHTML = "";
        host.classList.add("tutor-visual-root");

        if (why) {
            var whyBlock = document.createElement("div");
            whyBlock.className = "tutor-visual-why";
            whyBlock.innerHTML =
                '<h4 class="tutor-visual-why__label">Why this is wrong</h4>' +
                '<div class="tutor-visual-why__text examiq-math-block">' +
                escapeHtml(why).replace(/\n/g, "<br>") +
                "</div>";
            host.appendChild(whyBlock);
        }

        var stepsHost = document.createElement("div");
        stepsHost.className = "tutor-visual-steps";
        host.appendChild(stepsHost);

        var controls = document.createElement("div");
        controls.className = "tutor-visual-controls";
        host.appendChild(controls);

        var chartHost = document.createElement("div");
        chartHost.className = "tutor-visual-chart-host";
        host.appendChild(chartHost);

        var answerHost = document.createElement("div");
        answerHost.className = "tutor-visual-answer-host";
        host.appendChild(answerHost);

        function paint() {
            stepsHost.innerHTML = "";
            var visible = progressive ? revealed : steps.length;
            steps.slice(0, visible).forEach(function (step, index) {
                var card = document.createElement("div");
                card.className = "tutor-visual-step";
                var eqs = (step.equations || [])
                    .map(function (eq) {
                        var cls = "tutor-visual-eq";
                        if (
                            step.highlight &&
                            String(eq).indexOf(String(step.highlight)) !== -1
                        ) {
                            cls += " tutor-visual-eq--highlight";
                        }
                        return (
                            '<div class="' +
                            cls +
                            ' examiq-math-block">' +
                            prepareMathField(eq, "equation") +
                            "</div>"
                        );
                    })
                    .join("");
                card.innerHTML =
                    '<div class="tutor-visual-step__icon" aria-hidden="true">' +
                    (index + 1) +
                    "</div>" +
                    '<div class="tutor-visual-step__body">' +
                    '<p class="tutor-visual-step__title">' +
                    prepareMathField(step.title || "Step " + (index + 1), "label") +
                    "</p>" +
                    (step.operation
                        ? '<p class="tutor-visual-step__op">' +
                          prepareMathField(step.operation, "label") +
                          "</p>"
                        : "") +
                    '<div class="tutor-visual-eq-stack">' +
                    eqs +
                    "</div></div>";
                stepsHost.appendChild(card);
            });

            controls.innerHTML = "";
            if (progressive && revealed < steps.length) {
                var btn = document.createElement("button");
                btn.type = "button";
                btn.className = "btn-secondary btn-primary-sm tutor-visual-next";
                btn.textContent =
                    revealed === 0 ? "Show first step" : "Show next step";
                btn.addEventListener("click", function () {
                    revealed += 1;
                    paint();
                });
                controls.appendChild(btn);
            }

            chartHost.innerHTML = "";
            if (
                structured &&
                structured.chart &&
                (!progressive || revealed >= steps.length)
            ) {
                renderChart(chartHost, structured.chart);
            }

            answerHost.innerHTML = "";
            if (answer && (!progressive || revealed >= steps.length || !steps.length)) {
                answerHost.innerHTML =
                    '<div class="tutor-visual-answer">' +
                    '<span class="tutor-visual-answer__icon" aria-hidden="true">✓</span>' +
                    '<div><span class="tutor-visual-answer__label">Answer</span>' +
                    '<div class="tutor-visual-answer__value examiq-math-block">' +
                    prepareMathField(answer, "equation") +
                    "</div></div></div>";
            }

            katexRender(host);
        }

        if (!steps.length && !answer && !why) {
            if (options.raw) {
                var plain = plainTutorText(structured, options.raw);
                host.innerHTML =
                    '<div class="tutor-visual-fallback examiq-math-block">' +
                    escapeHtml(plain).replace(/\n/g, "<br>") +
                    "</div>";
                katexRender(host);
            }
            return { rebuild: paint };
        }

        paint();
        return { rebuild: paint };
    }

    window.ExamiQUI = window.ExamiQUI || {};
    window.ExamiQUI.renderTutorVisualResponse = renderVisualResponse;
    window.ExamiQUI.parseTutorStructured = parseStructured;
    window.ExamiQUI.extractFeedbackText = extractFeedbackText;
    window.ExamiQUI.plainTutorText = plainTutorText;
    window.ExamiQUI.isRichTutorResponse = isRichTutorResponse;
    window.ExamiQUI.isSolutionResponse = isSolutionResponse;
    window.ExamiQUI.looksLikePlainMathSolution = looksLikePlainMathSolution;
    window.ExamiQUI.wrapBareLatex = wrapBareLatex;
    window.ExamiQUI.stripLatexDecorations = stripLatexDecorations;
})();
