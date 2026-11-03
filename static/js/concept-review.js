(function () {
  "use strict";

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function qsa(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function csrfToken(root) {
    return (root && root.dataset.csrf) || "";
  }

  function postJson(url, token, body) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": token,
      },
      credentials: "same-origin",
      body: JSON.stringify(body || {}),
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) {
          throw new Error((data && data.error) || "Request failed");
        }
        return data;
      });
    });
  }

  /* Progress card lives outside the step partial, so update it in place
     instead of waiting for a full page reload. */
  function updateProgress(streak) {
    var fill = qs("#concept-progress-fill");
    var count = qs("#concept-progress-count");
    var target = parseInt((fill && fill.dataset.target) || "3", 10) || 3;
    var value = Math.max(0, Math.min(parseInt(streak, 10) || 0, target));
    if (fill) {
      fill.style.width = Math.round((value / target) * 100) + "%";
    }
    if (count) {
      count.textContent = String(value);
    }
  }

  function setBusy(btn, busy) {
    if (!btn) {
      return;
    }
    btn.disabled = busy;
    btn.classList.toggle("is-busy", busy);
    btn.setAttribute("aria-busy", busy ? "true" : "false");
    var text = qs(".concept-regen-btn__text", btn);
    if (text) {
      text.textContent = busy
        ? btn.dataset.regenBusyLabel || "Generating…"
        : btn.dataset.regenLabel || "Change question";
    }
  }

  function renderMath(el) {
    if (!el || typeof renderMathInElement === "undefined") {
      return;
    }
    var options = window.ExamiQKatex && window.ExamiQKatex.options;
    if (!options) {
      options = {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "$", right: "$", display: false },
        ],
        throwOnError: false,
      };
    }
    renderMathInElement(el, options);
  }

  function initTryIt(root) {
    var checkBtn = qs("#try-it-check", root);
    var hintBtn = qs("#try-it-hint", root);
    var feedback = qs("#try-it-feedback", root);
    var hintText = qs("#try-it-hint-text", root);
    var continueLink = qs("#try-it-continue", root);
    if (!checkBtn) {
      return;
    }

    var url = root.dataset.tryItUrl;
    var token = csrfToken(root);

    checkBtn.addEventListener("click", function () {
      var selected = qs('input[name="try_it_choice"]:checked', root);
      if (!selected) {
        feedback.textContent = "Select a first step first.";
        feedback.classList.remove("hidden");
        return;
      }
      checkBtn.disabled = true;
      postJson(url, token, { choice_index: parseInt(selected.value, 10) })
        .then(function (data) {
          qsa(".concept-option", qs("#try-it-options", root)).forEach(function (label) {
            label.classList.remove("is-wrong", "is-correct");
          });
          var label = selected.closest(".concept-option");
          if (data.is_correct) {
            if (label) {
              label.classList.add("is-correct");
            }
            feedback.classList.add("hidden");
            if (continueLink) {
              continueLink.classList.remove("hidden");
            }
            checkBtn.classList.add("hidden");
          } else {
            if (typeof data.correct_index === "number") {
              var correct = qsa(".concept-option", qs("#try-it-options", root))[data.correct_index];
              if (correct && correct !== label) {
                correct.classList.add("is-correct");
              }
            }
            if (label) {
              label.classList.add("is-wrong");
            }
            feedback.textContent = data.feedback || "Not quite. Try again.";
            feedback.classList.remove("hidden");
            renderMath(feedback);
            checkBtn.disabled = false;
          }
        })
        .catch(function (err) {
          feedback.textContent = err.message || "Could not check answer.";
          feedback.classList.remove("hidden");
          checkBtn.disabled = false;
        });
    });

    if (hintBtn && hintText) {
      hintBtn.addEventListener("click", function () {
        var trySection = qs("#concept-try-it", root);
        hintText.textContent =
          (trySection && trySection.dataset.hint) ||
          "Undo the constant term before touching the coefficient.";
        hintText.classList.remove("hidden");
        var reminder = qs("#try-it-reminder", root);
        if (reminder) reminder.classList.remove("hidden");
        renderMath(hintText);
      });
    }
  }

  function fillPracticeOptions(container, options) {
    if (!container) {
      return;
    }
    container.innerHTML = "";
    var legend = document.createElement("legend");
    legend.className = "sr-only";
    legend.textContent = "Answer choices";
    container.appendChild(legend);
    (options || []).forEach(function (opt, index) {
      var label = document.createElement("label");
      label.className = "concept-option";
      label.dataset.optionId = opt.id;
      var input = document.createElement("input");
      input.type = "radio";
      input.name = "practice_choice";
      input.value = opt.id;
      input.className = "sr-only";
      var badge = document.createElement("span");
      badge.className = "concept-option__badge";
      badge.setAttribute("aria-hidden", "true");
      badge.textContent = ["A", "B", "C", "D"][index] || String(index + 1);
      var span = document.createElement("span");
      span.textContent = opt.text;
      label.appendChild(input);
      label.appendChild(badge);
      label.appendChild(span);
      container.appendChild(label);
    });
    renderMath(container);
  }

  function initPractice(root) {
    var section = qs("#concept-practice", root);
    if (!section || section.dataset.resolved === "1") {
      return;
    }
    var checkBtn = qs("#practice-check", root);
    var hintBtn = qs("#practice-hint", root);
    var nextBtn = qs("#practice-next", root);
    var regenBtn = qs("#practice-regenerate", root);
    var feedback = qs("#practice-feedback", root);
    var hintText = qs("#practice-hint-text", root);
    var solution = qs("#practice-solution", root);
    var questionEl = qs("#practice-question", root);
    var optionsEl = qs("#practice-options", root);
    var url = root.dataset.practiceUrl;
    var token = csrfToken(root);

    function currentAttemptId() {
      return section.dataset.attemptId || "";
    }

    if (hintBtn && hintText) {
      hintBtn.addEventListener("click", function () {
        hintText.textContent =
          hintText.dataset.hint ||
          section.dataset.hint ||
          "Start by undoing the outermost operation.";
        hintText.classList.remove("hidden");
        var reminder = qs("#practice-reminder", root);
        if (reminder) reminder.classList.remove("hidden");
        renderMath(hintText);
      });
    }

    if (checkBtn) {
      checkBtn.addEventListener("click", function () {
        var selected = qs('input[name="practice_choice"]:checked', root);
        if (!selected) {
          feedback.textContent = "Select an option first.";
          feedback.classList.remove("hidden");
          return;
        }
        checkBtn.disabled = true;
        postJson(url, token, {
          action: "check",
          attempt_id: currentAttemptId(),
          option_id: selected.value,
        })
          .then(function (data) {
            qsa(".concept-option", optionsEl).forEach(function (label) {
              label.classList.remove("is-wrong", "is-correct");
              if (data.correct_option_id && label.dataset.optionId === data.correct_option_id) {
                label.classList.add("is-correct");
              }
            });
            var label = selected.closest(".concept-option");
            if (data.is_correct) {
              if (label) {
                label.classList.add("is-correct");
              }
              updateProgress(data.correct_streak);
              feedback.classList.add("hidden");
              if (solution) {
                var steps = (data.solution_steps || []).join(" ");
                solution.textContent =
                  (steps ? steps + " " : "") +
                  (data.final_answer ? "Answer: " + data.final_answer : "");
                solution.classList.remove("hidden");
                renderMath(solution);
              }
              if (data.resolved && data.redirect_url) {
                window.location.href = data.redirect_url;
                return;
              }
              if (nextBtn) {
                nextBtn.classList.remove("hidden");
              }
              checkBtn.classList.add("hidden");
            } else {
              if (label) {
                label.classList.add("is-wrong");
              }
              feedback.textContent = data.why_wrong || "Not quite. Try another approach.";
              feedback.classList.remove("hidden");
              renderMath(feedback);
              if (data.hint) {
                hintText.dataset.hint = data.hint;
              }
              checkBtn.disabled = false;
            }
          })
          .catch(function (err) {
            feedback.textContent = err.message || "Could not check answer.";
            feedback.classList.remove("hidden");
            checkBtn.disabled = false;
          });
      });
    }

    if (nextBtn || regenBtn) {
      // Shared loader for both "Next question" and "Change question".
      function loadNextQuestion(action, trigger) {
        var isRegen = action === "regenerate";
        if (trigger) trigger.disabled = true;
        if (checkBtn) checkBtn.disabled = true;
        // Regenerating is a fresh AI call, so show a spinner for its duration.
        if (isRegen) {
          setBusy(trigger, true);
        }
        postJson(url, token, { action: action })
          .then(function (data) {
            if (isRegen) {
              // The page re-renders the new question, hint and progress from
              // the database, which keeps everything in sync server-side.
              window.location.reload();
              return;
            }
            var payload = data.payload || {};
            section.dataset.attemptId = String(data.attempt_id || "");
            if (questionEl) {
              questionEl.textContent = payload.question || "";
              renderMath(questionEl);
              formatQuestion(questionEl);
            }
            fillPracticeOptions(optionsEl, payload.options || []);
            if (payload.hint) {
              hintText.dataset.hint = payload.hint;
              section.dataset.hint = payload.hint;
            }
            feedback.classList.add("hidden");
            hintText.classList.add("hidden");
            if (solution) {
              solution.classList.add("hidden");
              solution.textContent = "";
            }
            if (nextBtn) {
              nextBtn.classList.add("hidden");
              nextBtn.disabled = false;
            }
            if (checkBtn) {
              checkBtn.classList.remove("hidden");
              checkBtn.disabled = true;
            }
          })
          .catch(function (err) {
            feedback.textContent = err.message || "Could not load the next question.";
            feedback.classList.remove("hidden");
            if (isRegen) {
              setBusy(trigger, false);
            } else if (trigger) {
              trigger.disabled = false;
            }
            if (checkBtn) checkBtn.disabled = false;
          });
      }

      if (nextBtn) {
        nextBtn.addEventListener("click", function () {
          loadNextQuestion("next", nextBtn);
        });
      }

      if (regenBtn) {
        regenBtn.addEventListener("click", function () {
          loadNextQuestion("regenerate", regenBtn);
        });
      }
    }

    renderMath(section);
  }

  /* Footer check buttons stay disabled until an option is selected. */
  function initCheckGating(root) {
    var pairs = [
      ["#try-it-check", 'input[name="try_it_choice"]'],
      ["#practice-check", 'input[name="practice_choice"]'],
    ];
    pairs.forEach(function (pair) {
      var btn = qs(pair[0], root);
      if (!btn) return;
      var note = btn.parentElement
        ? qs("[data-hint-note]", btn.parentElement)
        : null;
      var sync = function () {
        var picked = !!qs(pair[1] + ":checked", root);
        btn.disabled = !picked;
        if (note) {
          if (picked) note.setAttribute("hidden", "");
          else note.removeAttribute("hidden");
        }
      };
      root.addEventListener("change", function (e) {
        if (e.target && e.target.matches(pair[1])) sync();
      });
      sync();
    });
  }

  /* Split "Sentence $math$." headings into a 20px sentence line and a
     28px equation line. Only fires for a single math node with real
     leading text and at most trailing punctuation; tolerates one
     wrapper element around the KaTeX output. Idempotent. */
  function formatQuestion(head) {
    if (!head || head.querySelector(".concept-question__equation")) return;
    var candidates = head.querySelectorAll(".katex-display, .katex");
    var tops = [];
    var i, m, p, nested;
    for (i = 0; i < candidates.length; i++) {
      m = candidates[i];
      nested = false;
      p = m.parentNode;
      while (p && p !== head) {
        if (
          p.nodeType === 1 &&
          (p.classList.contains("katex") ||
            p.classList.contains("katex-display"))
        ) {
          nested = true;
          break;
        }
        p = p.parentNode;
      }
      if (!nested) tops.push(m);
    }
    if (tops.length !== 1) return;
    var top = tops[0];
    var anchor = top;
    while (anchor.parentNode !== head) {
      anchor = anchor.parentNode;
    }
    var leading = "";
    var node = head.firstChild;
    while (node && node !== anchor) {
      leading += node.textContent || "";
      node = node.nextSibling;
    }
    if (!leading.trim()) return;
    var trailing = "";
    node = anchor.nextSibling;
    while (node) {
      trailing += node.textContent || "";
      node = node.nextSibling;
    }
    if (trailing.trim() && !/^[.,;:!?)\]\s]*$/.test(trailing)) return;
    var sentence = document.createElement("span");
    sentence.className = "concept-question__sentence";
    node = head.firstChild;
    while (node && node !== anchor) {
      var next = node.nextSibling;
      sentence.appendChild(node);
      node = next;
    }
    var equation = document.createElement("span");
    equation.className = "concept-question__equation";
    while (head.firstChild) {
      equation.appendChild(head.firstChild);
    }
    head.appendChild(sentence);
    head.appendChild(equation);
  }

  function init() {
    var root = qs("#review-overlay");
    if (!root) {
      return;
    }
    document.body.classList.add("review-open");
    renderMath(root);
    qsa(".concept-question", root).forEach(formatQuestion);
    initCheckGating(root);
    if (root.dataset.step === "try_it") {
      initTryIt(root);
    }
    if (root.dataset.step === "practice") {
      initPractice(root);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
