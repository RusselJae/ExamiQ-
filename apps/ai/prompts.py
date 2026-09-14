"""Prompt builders ported from the legacy ExamiQ PHP API (api.php).

Each builder returns (system_instruction, user_prompt) unless noted.
Token budgets are returned as a third value where generation may truncate.
"""

from __future__ import annotations

import json
from typing import Any

from apps.questions.models import Question

# ---------------------------------------------------------------------------
# Shared persona and rules (legacy: chatGPT, ai_chat, buildAdaptivePrompt)
# ---------------------------------------------------------------------------

EXAMIQ_PERSONA = "ExamiQ+"

MATH_NOTATION_RULES = """\
### RULES FOR MATH NOTATION
- Do NOT use LaTeX, $ symbols, or complex math notation.
- Use plain text formulas only. Example: area = length x width
- For multiplication, use 'x' or 'times'. For division, use '/' or 'divided by'.
- For exponents use caret: m^2, ft^3, 2^4
- When explaining (not MCQ JSON), prefer proper symbols: √ × ÷ ± ≈ π and subscripts x₁ x₂ \
when the student can read them; otherwise explain the symbol in plain English.
- If the student seems confused, rewrite formulas in simple English."""

TUTOR_RESPONSE_STYLE = """\
### RESPONSE STYLE
- Prefer structured JSON (see output schema). Keep reasoning tight.
- Math with KaTeX-friendly $...$ / $$...$$ when equations help.
- Do not add long practice-recommendation essays unless the student asks."""

TUTOR_CHAT_JSON_SCHEMA = """\
Return ONLY a JSON object (no markdown fences). Use ONE of these shapes:

Text reply (conceptual / short follow-ups):
{"type": "text", "content": "plain explanation..."}

Solution reply (step-by-step solve):
{
  "type": "solution",
  "steps": [
    {
      "title": "short step title",
      "operation": "what rule you applied (e.g. divide both sides by 3)",
      "equations": ["$3x = 12$", "$x = 4$"],
      "highlight": "optional term that changed"
    }
  ],
  "answer": "$x = 4$",
  "chart": null
}

Optional chart (ONLY when a diagram clarifies optimization, geometry, or motion — otherwise null):
{
  "type": "line",
  "title": "short chart title",
  "points": [[0, 10], [5, 2], [10, 10]],
  "markers": [{"x": 5, "label": "x = 5 (minimum)"}]
}

Rules for solution steps:
- Stack equations aligned conceptually (each transformation on its own line).
- Annotate the operation; do not dump paragraph prose.
- Put the final result in "answer" separately from scratch work.
- Keep "title" and "operation" in plain English; put all math in "equations" and "answer" wrapped in $...$."""

TUTOR_CHAT_RULES = """\
RULES:
- Do NOT greet the user or introduce yourself.
- Respond with the JSON schema only.
- Short conceptual questions → {"type": "text", "content": "..."}.
- Requests to solve, show steps, or show the complete solution → {"type": "solution", "steps": [...], "answer": "..."}.
- NEVER return a plain numbered prose list for solve requests — always use type solution JSON.
- If the message is vague, tie it to the active question in step 1, then help.
- Use $...$ / $$...$$ for math (KaTeX).
- Do not put LaTeX commands in "title" or "operation"."""

ADAPTIVE_TOPIC_RESTRICTION = """\
### TOPIC RESTRICTION (IMPORTANT)
You must ONLY answer questions related to the current topic.

If the student asks something outside this topic:
- Do NOT answer the unrelated question.
- Redirect them politely and keep them focused on the current lesson."""

CONFIDENCE_ADAPTIVE_RULES = """\
### CONFIDENCE-ADAPTIVE BEHAVIOR
- Low confidence: slow, simple, supportive explanations.
- Medium confidence: balanced explanation.
- High confidence: deeper reasoning; remind them to check work when needed.

### FORMATTING RULES
- Use plain sentences. Avoid decorative symbols (arrows, bullets, equals signs, markdown headers).
- Only use math symbols when the question, answer, or solution already uses them.
- For incorrect answers, include numbered step-by-step correction (Step 1, Step 2, ...).
- Keep each step on its own line."""

AI_FEEDBACK_JSON_RULES = """\
CRITICAL JSON FORMATTING RULES:
- Use proper JSON string escaping.
- For correction_steps: use ACTUAL newlines in the JSON string (not literal backslash-n).
- Use plain language. Avoid decorative symbols unless math notation appears in the question.
- correction_steps must be numbered steps (Step 1, Step 2, ...) with one action per step.
- Return ONLY the JSON object — no markdown fences or prose."""

AI_FEEDBACK_JSON_SCHEMA = """\
{
  "success": true,
  "topic": "<topic_name>",
  "items": [
    {
      "question": "<the_question_text>",
      "user_answer": "<what_student_answered>",
      "correct_answer": "<the_correct_answer>",
      "why_wrong": "<explanation_of_error>",
      "correction_steps": "Step 1: ...\\nStep 2: ...\\nStep 3: ...",
      "recommended_concepts": ["concept1", "concept2"],
      "recommended_difficulty": "easy|medium|hard"
    }
  ],
  "overall_recommendations": ["...", "..."]
}"""

QUESTION_VALIDATION_JSON_SCHEMA = (
    '{"is_valid": true/false, "topic_relevant": true/false, '
    '"answer_correct": true/false, "feedback": "3-6 sentences with specific guidance", '
    '"suggested_concept_tag": "short label"}'
)

QUESTION_JSON_SCHEMA = (
    '[{"question_type":"mcq","stem":"short question text","concept_tag":"2-4 word tag",'
    '"correct_label":"B",'
    '"choices":[{"label":"A","text":"plausible distractor","is_correct":false},'
    '{"label":"B","text":"the one correct answer","is_correct":true},'
    '{"label":"C","text":"plausible distractor","is_correct":false},'
    '{"label":"D","text":"plausible distractor","is_correct":false}]}'
)

TRUE_FALSE_JSON_SCHEMA = (
    '[{"question_type":"true_false","stem":"A clear true or false statement.",'
    '"concept_tag":"2-4 word tag","expected_answer":"True"}]'
)

IDENTIFICATION_JSON_SCHEMA = (
    '[{"question_type":"identification","stem":"Name the property used here.",'
    '"concept_tag":"2-4 word tag","expected_answer":"commutative property"}]'
)

ENUMERATION_JSON_SCHEMA = (
    '[{"question_type":"enumeration","stem":"List the three measures of central tendency.",'
    '"concept_tag":"2-4 word tag","expected_answer":"mean\\nmedian\\nmode"}]'
)

EXPLANATION_JSON_SCHEMA = (
    '{"explanation_steps":['
    '"Align like terms.",'
    '"x^2 + 2x^2 = 3x^2",'
    '"Write the final answer: 3x^2 + x + 7"'
    '],'
    '"solution_summary":"Final answer: B"}'
)

DIFFICULTY_GUIDANCE: dict[str, str] = {
    "easy": (
        "Beginner: single concept, direct recall or one obvious step. "
        "Stem tests definition, identification, or a basic application."
    ),
    "medium": (
        "Intermediate: combine 2-3 ideas, moderate reasoning or multi-step setup. "
        "Distractors should tempt partial understanding."
    ),
    "hard": (
        "Advanced: deep understanding required — NOT beginner questions with harder wording. "
        "Use scenario-based stems (language acceptance, construction, optimization, proof, "
        "debugging, edge cases, trade-offs). "
        "Applies to every subject (CS theory, discrete math, programming, statistics, "
        "algebra, geometry, etc.). "
        "Distractors must reflect real misconceptions experts see in this topic."
    ),
}

# Legacy tutorQA topic keywords — useful for off-topic redirects in tutor flows.
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "algebra": ["solve", "equation", "x", "variable", "polynomial", "factor"],
    "geometry": [
        "triangle",
        "angle",
        "circle",
        "area",
        "perimeter",
        "shape",
        "sides",
        "radius",
        "diameter",
    ],
    "calculus": ["derivative", "integral", "limit", "rate of change"],
    "logic": ["statement", "truth table", "logic", "proposition", "if and only if"],
    "statistics": ["mean", "median", "mode", "probability", "distribution"],
    "programming": ["function", "loop", "array", "variable", "algorithm", "code"],
    "data structures": ["stack", "queue", "tree", "graph", "linked list", "hash"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def difficulty_label(difficulty: str) -> str:
    try:
        return Question.Difficulty(difficulty).label
    except ValueError:
        return difficulty


def format_pattern_text(patterns: list[str] | None) -> str:
    if not patterns:
        return "No recurring mistakes yet."
    return "Detected recurring mistakes:\n- " + "\n- ".join(patterns)


def format_exam_context(exam_context: dict[str, Any] | None) -> str:
    if not exam_context:
        return ""
    parts: list[str] = []
    if exam_context.get("exam_name"):
        parts.append(f"The student recently took an exam: {exam_context['exam_name']}")
    if exam_context.get("subject"):
        parts.append(f"on the subject of {exam_context['subject']}")
    if exam_context.get("topic"):
        parts.append(f"covering the topic {exam_context['topic']}")
    if not parts:
        return ""
    return "Context: " + " ".join(parts) + "\n\n"


def format_conversation_history(history: list[dict[str, str]] | None) -> str:
    if not history:
        return ""
    lines: list[str] = []
    for turn in history:
        role = (turn.get("role") or "user").lower().strip()
        text = (turn.get("text") or turn.get("message") or "").strip()
        if not text:
            continue
        prefix = "Assistant" if role in ("assistant", "bot") else "User"
        lines.append(f"{prefix}: {text}")
    if not lines:
        return ""
    return "Conversation so far:\n" + "\n".join(lines) + "\n\n"


GENERATABLE_QUESTION_TYPES = frozenset(
    {
        Question.QuestionType.MCQ,
        Question.QuestionType.TRUE_FALSE,
        Question.QuestionType.IDENTIFICATION,
        Question.QuestionType.ENUMERATION,
    }
)


def coerce_generate_question_type(value: str | None) -> str:
    """Return a supported generate type; default to MCQ."""
    key = (value or "").strip().lower()
    if key in GENERATABLE_QUESTION_TYPES:
        return key
    return Question.QuestionType.MCQ


def question_generation_max_tokens(count: int, difficulty: str = "") -> int:
    """Budget for MCQ-only generation (explanations are a separate call)."""
    from django.conf import settings

    cap = getattr(settings, "GEMINI_QUESTION_MAX_OUTPUT_TOKENS", 2048)
    base = max(900, 220 * count)
    if difficulty == Question.Difficulty.HARD:
        base = int(base * 1.35)
    return min(cap, base)


def explanation_generation_max_tokens() -> int:
    """Budget for a single question's explanation JSON."""
    from django.conf import settings

    cap = getattr(settings, "GEMINI_QUESTION_MAX_OUTPUT_TOKENS", 2048)
    return min(cap, 2500)


def adaptive_feedback_max_tokens() -> int:
    """Budget for per-answer adaptive feedback text."""
    from django.conf import settings

    cap = getattr(settings, "GEMINI_QUESTION_MAX_OUTPUT_TOKENS", 2048)
    return min(cap, 1200)


def validation_max_tokens() -> int:
    """Budget for professor question validation JSON."""
    from django.conf import settings

    cap = getattr(settings, "GEMINI_QUESTION_MAX_OUTPUT_TOKENS", 2048)
    return min(cap, 1000)


def exam_feedback_max_tokens(item_count: int) -> int:
    """Budget for batch/single exam feedback JSON (legacy chunk size ~6)."""
    from django.conf import settings

    cap = getattr(settings, "GEMINI_QUESTION_MAX_OUTPUT_TOKENS", 2048)
    return min(cap, max(1200, 400 * max(item_count, 1)))


def _keyword_in_text(word: str, text: str) -> bool:
    import re

    if len(word) <= 2:
        return bool(re.search(rf"\b{re.escape(word)}\b", text))
    return word in text


def off_topic_redirect(topic: str, question: str) -> str | None:
    """Return a redirect message if the question matches another topic's keywords."""
    topic_lower = topic.lower().strip()
    question_lower = question.lower()
    for other_topic, keywords in TOPIC_KEYWORDS.items():
        if other_topic == topic_lower:
            continue
        for word in keywords:
            if not _keyword_in_text(word, question_lower):
                continue
            return (
                f"That question belongs to **{other_topic.title()}**, but we are "
                f"currently studying **{topic.strip()}**.\n\n"
                f"Ask something related to **{topic.strip()}** so I can help you better!"
            )
    return None


# ---------------------------------------------------------------------------
# Question generation (professor AI generate / variations)
# ---------------------------------------------------------------------------

QUESTION_GENERATION_SYSTEM_MCQ = (
    f"You are {EXAMIQ_PERSONA} question writer. Return valid JSON only — no markdown, no prose.\n"
    "Rules:\n"
    "- MCQ with exactly 4 distinct non-empty choices (A-D); exactly one correct.\n"
    "- correct_label MUST match the single choice with is_correct:true.\n"
    "- Randomize correct_label per question (A, B, C, or D). Never default all answers to A.\n"
    "- In a batch, use at least 2 different correct_label values when count ≥ 2.\n"
    "- Stems ≤50 words; choice text ≤120 characters; difficulty must match requested level.\n"
    "- Distractors plausible but definitively wrong to a subject expert.\n"
    "- Solve each problem yourself before marking the answer; verify correctness.\n"
    "- Do NOT include explanation_steps or solution_summary — questions only.\n"
    "JSON output rules:\n"
    "- Return ONLY a raw JSON array. No markdown fences or commentary.\n"
    "- No trailing commas. Escape double quotes inside strings.\n"
    "Use plain text for formulas — no LaTeX or markdown."
)

QUESTION_GENERATION_SYSTEM_TRUE_FALSE = (
    f"You are {EXAMIQ_PERSONA} question writer. Return valid JSON only — no markdown, no prose.\n"
    "Rules:\n"
    "- Each item is a True or False statement (not a question with choices).\n"
    "- expected_answer must be exactly True or False.\n"
    "- Stems ≤50 words; difficulty must match requested level.\n"
    "- Do NOT include explanation_steps or solution_summary.\n"
    "JSON output rules:\n"
    "- Return ONLY a raw JSON array. No markdown fences or commentary.\n"
    "- No trailing commas. Escape double quotes inside strings."
)

QUESTION_GENERATION_SYSTEM_IDENTIFICATION = (
    f"You are {EXAMIQ_PERSONA} question writer. Return valid JSON only — no markdown, no prose.\n"
    "Rules:\n"
    "- Each item asks for a short fill-in answer (term, value, or name).\n"
    "- expected_answer must be concise and unambiguous (case does not matter for grading).\n"
    "- Avoid answers that depend on capitalization unless the concept requires it.\n"
    "- Stems ≤50 words; difficulty must match requested level.\n"
    "- Do NOT include explanation_steps or solution_summary.\n"
    "JSON output rules:\n"
    "- Return ONLY a raw JSON array. No markdown fences or commentary.\n"
    "- No trailing commas. Escape double quotes inside strings."
)

QUESTION_GENERATION_SYSTEM_ENUMERATION = (
    f"You are {EXAMIQ_PERSONA} question writer. Return valid JSON only — no markdown, no prose.\n"
    "Rules:\n"
    "- Each item asks the student to list at least two related items.\n"
    "- expected_answer must list items one per line (use \\n between items).\n"
    "- Stems ≤50 words; difficulty must match requested level.\n"
    "- Do NOT include explanation_steps or solution_summary.\n"
    "JSON output rules:\n"
    "- Return ONLY a raw JSON array. No markdown fences or commentary.\n"
    "- No trailing commas. Escape double quotes inside strings."
)

EXPLANATION_GENERATION_SYSTEM = (
    f"You are {EXAMIQ_PERSONA} solution writer. Return valid JSON only — no markdown, no prose.\n"
    "Rules:\n"
    "- Provide a complete worked solution matched to the question type (see user prompt).\n"
    "- explanation_steps: 4-6 substantive steps for multi-step work; 3-4 for simpler items.\n"
    "- Each step may be 1-2 sentences OR one math line — teach the reasoning, not just the answer.\n"
    "- Start instructional steps with an action verb (Identify, Set up, Substitute, Solve, Check).\n"
    "- Name the rule, formula, or concept when it helps the student understand why.\n"
    "- Use plain, direct language a student can follow after missing the question.\n"
    "- Avoid vague lines like 'do the calculation' or 'apply the formula' without showing what.\n"
    "- solution_summary is one clear line stating the final answer.\n"
    "- For math-heavy subjects you may use KaTeX-friendly $...$ in steps.\n"
    "- For non-math subjects use plain English only.\n"
    "JSON output rules:\n"
    "- Return ONLY a raw JSON object. No markdown fences or commentary.\n"
    "- No trailing commas. Escape double quotes inside strings."
)


def _explanation_type_guidance(qtype: str) -> str:
    from apps.questions.models import Question as QuestionModel

    if qtype == QuestionModel.QuestionType.TRUE_FALSE:
        return (
            "True/False: state clearly whether the claim is True or False, explain why "
            "with the key fact or rule, and note a common misconception if relevant.\n"
        )
    if qtype == QuestionModel.QuestionType.IDENTIFICATION:
        return (
            "Identification: give the expected term/phrase, how to recognize it in context, "
            "and a spelling or case note if helpful.\n"
        )
    if qtype == QuestionModel.QuestionType.ENUMERATION:
        return (
            "Enumeration: put each required list item on its own step with a brief why; "
            "note if order matters.\n"
        )
    if qtype == QuestionModel.QuestionType.NUMERIC:
        return (
            "Numeric: show full calculation steps with intermediate values; end with the "
            "final numeric answer and a quick reasonableness check if useful.\n"
        )
    return (
        "MCQ: explain why the correct choice is right, why each major distractor is wrong, "
        "and the concept that ties the problem together.\n"
    )


def _explanation_math_rules(subject) -> str:
    name = (getattr(subject, "name", "") or "").lower()
    code = (getattr(subject, "code", "") or "").lower()
    math_hints = ("math", "algebra", "geometry", "trigonometry", "calculus", "statistics")
    if any(hint in name or hint in code for hint in math_hints):
        return "Use $...$ for formulas and equations in explanation_steps.\n"
    return "Use plain English; avoid LaTeX.\n"


def _difficulty_guidance(difficulty: str) -> str:
    return DIFFICULTY_GUIDANCE.get(difficulty, DIFFICULTY_GUIDANCE["medium"])


def build_question_generation_prompt(
    topic,
    difficulty: str,
    count: int,
    reference_stem: str = "",
    source_material: str = "",
    question_type: str = "mcq",
) -> tuple[str, str, int]:
    """Return (system_instruction, user_prompt, max_output_tokens)."""
    qtype = coerce_generate_question_type(question_type)
    subject = topic.subject
    label = difficulty_label(difficulty)
    ref = reference_stem.strip() or "none"
    material = (source_material or "").strip()
    material_block = (
        f"Learning material (base questions on this content):\n{material}\n\n"
        if material
        else ""
    )
    guidance = _difficulty_guidance(difficulty)
    type_labels = {
        Question.QuestionType.MCQ: "multiple-choice",
        Question.QuestionType.TRUE_FALSE: "true or false",
        Question.QuestionType.IDENTIFICATION: "identification (fill-in)",
        Question.QuestionType.ENUMERATION: "enumeration (list items)",
    }
    type_label = type_labels.get(qtype, "multiple-choice")

    if qtype == Question.QuestionType.TRUE_FALSE:
        system = QUESTION_GENERATION_SYSTEM_TRUE_FALSE
        schema = TRUE_FALSE_JSON_SCHEMA
        extra = "Write clear statements that are definitively True or False.\n"
    elif qtype == Question.QuestionType.IDENTIFICATION:
        system = QUESTION_GENERATION_SYSTEM_IDENTIFICATION
        schema = IDENTIFICATION_JSON_SCHEMA
        extra = (
            "Keep expected_answer short. Grading ignores capitalization and extra spaces.\n"
        )
    elif qtype == Question.QuestionType.ENUMERATION:
        system = QUESTION_GENERATION_SYSTEM_ENUMERATION
        schema = ENUMERATION_JSON_SCHEMA
        extra = "List at least two items in expected_answer, one per line.\n"
    else:
        system = QUESTION_GENERATION_SYSTEM_MCQ
        schema = QUESTION_JSON_SCHEMA
        extra = (
            "Keep stems and choice text short. Escape quotes inside JSON strings.\n"
            "Pick a different correct_label for each question when possible (mix A, B, C, D).\n"
            "Do NOT place the correct answer on the same letter for every question.\n"
        )

    year_level = getattr(subject, "year_level", None)
    year_label = year_level.name if year_level else "unspecified"
    year_order = year_level.order if year_level else ""
    year_hint = (
        f"Year level: {year_label}"
        + (f" (year {year_order})" if year_order != "" else "")
        + ". Match college-level BSEd Mathematics expectations for this year — "
        "not high school review and not graduate-level depth.\n"
    )

    user_prompt = (
        f"Generate exactly {count} {type_label} questions.\n"
        f"Topic: {topic.name} | Subject: {subject.code} – {subject.name}\n"
        f"{year_hint}"
        f"Difficulty: {label} ({difficulty})\n"
        f"Question type: {qtype}\n"
        f"{guidance}\n"
        f"Reference (optional): {ref}\n\n"
        f"{material_block}"
        f"{extra}"
        "Return questions only — omit explanation_steps and solution_summary.\n"
        f"JSON array schema:\n{schema}"
    )
    return system, user_prompt, question_generation_max_tokens(count, difficulty)


def build_explanation_generation_prompt(question) -> tuple[str, str, int]:
    """Return (system_instruction, user_prompt, max_output_tokens) for one question."""
    from apps.questions.models import Question as QuestionModel

    topic = question.topic
    subject = topic.subject
    qtype = question.question_type or QuestionModel.QuestionType.MCQ

    if qtype == QuestionModel.QuestionType.MCQ:
        choices = list(question.choices.order_by("label"))
        choices_payload = [
            {
                "label": choice.label,
                "text": choice.text,
                "is_correct": choice.is_correct,
            }
            for choice in choices
        ]
        correct = next((c for c in choices if c.is_correct), None)
        correct_label = correct.label if correct else ""
        answer_block = (
            f"Choices: {json.dumps(choices_payload)}\n"
            f"Correct label: {correct_label}\n"
        )
    elif qtype == QuestionModel.QuestionType.NUMERIC:
        answer_block = f"Correct numeric answer: {question.correct_answer}\n"
    else:
        answer_block = f"Expected answer: {question.expected_answer}\n"

    type_guidance = _explanation_type_guidance(qtype)
    math_rules = _explanation_math_rules(subject)
    system = EXPLANATION_GENERATION_SYSTEM

    user_prompt = (
        f"Write explanation_steps and solution_summary for this {qtype} question.\n"
        f"Topic: {topic.name} | Subject: {subject.code} – {subject.name}\n"
        f"Difficulty: {difficulty_label(question.difficulty)}\n"
        f"Stem: {question.stem}\n"
        f"{answer_block}\n"
        f"{type_guidance}"
        f"{math_rules}"
        "Write a complete worked solution a student can study after a mistake — concrete, "
        "ordered, and thorough without repeating the question stem verbatim.\n"
        "Use full steps; escape quotes inside JSON strings.\n"
        f"JSON object schema:\n{EXPLANATION_JSON_SCHEMA}"
    )
    return (
        system,
        user_prompt,
        explanation_generation_max_tokens(),
    )


# ---------------------------------------------------------------------------
# Question validation (professor validate modal)
# ---------------------------------------------------------------------------

QUESTION_VALIDATION_SYSTEM = (
    f"You are {EXAMIQ_PERSONA} exam reviewer. Return valid JSON only.\n"
    "Structural checks: stem is clear; exactly 4 choices A-D with distinct text; "
    "exactly one marked correct; correct_label matches the true answer.\n"
    "Semantic checks: solve the problem independently; confirm the stem fits the "
    "named course subject and topic; confirm difficulty fits.\n"
    "Set topic_relevant:false when the stem is off-subject for the named course.\n"
    "When topic_relevant is false, feedback MUST name the subject code and explain why.\n"
    "feedback must be helpful and specific (3-6 sentences): what failed, why it matters, "
    "and what to fix — not a bare error list.\n"
    "Set is_valid:false if ANY check fails. Be strict — do not pass flawed questions."
)


def build_question_validation_prompt(
    stem: str,
    choices: list[dict],
    topic,
    difficulty: str,
    correct_label: str = "",
) -> tuple[str, str]:
    subject = topic.subject if topic and hasattr(topic, "subject") else None
    subject_code = getattr(subject, "code", "") or ""
    subject_name = getattr(subject, "name", "") if subject else ""
    topic_name = topic.name if topic else ""
    choices_text = json.dumps(choices)
    user_prompt = (
        f"Validate this MCQ for course subject '{subject_code} — {subject_name}', "
        f"topic '{topic_name}', difficulty '{difficulty}'.\n"
        f"Stem: {stem}\nChoices: {choices_text}\nMarked correct: {correct_label}\n\n"
        "Solve the problem yourself. Verify the marked choice is definitively correct.\n"
        "Reject if off-subject for this course, choices are duplicated/ambiguous, "
        "or the marked answer is wrong.\n"
        f"Return JSON only:\n{QUESTION_VALIDATION_JSON_SCHEMA}"
    )
    return QUESTION_VALIDATION_SYSTEM, user_prompt


# ---------------------------------------------------------------------------
# Tutor chat (legacy: ai_chat) — future student tutor UI
# ---------------------------------------------------------------------------

TUTOR_CHAT_SYSTEM = (
    f"You are {EXAMIQ_PERSONA}, a clear and friendly tutor for math and computer science.\n"
    "Use KaTeX-friendly math with $...$ or $$...$$ when equations help.\n"
    f"{TUTOR_RESPONSE_STYLE}\n{TUTOR_CHAT_JSON_SCHEMA}"
)


def format_question_context(question_context: dict[str, Any] | None) -> str:
    if not question_context:
        return ""
    parts = []
    if question_context.get("stem"):
        parts.append(f"Current question: {question_context['stem']}")
    if question_context.get("user_answer"):
        parts.append(f"Student answer: {question_context['user_answer']}")
    if question_context.get("correct_answer"):
        parts.append(f"Correct answer: {question_context['correct_answer']}")
    if "is_correct" in question_context:
        parts.append(f"Was correct: {question_context['is_correct']}")
    if question_context.get("timed_out"):
        parts.append("Student timed out on this question.")
    if question_context.get("difficulty"):
        parts.append(f"Difficulty: {question_context['difficulty']}")
    if not parts:
        return ""
    return "Active question context:\n" + "\n".join(f"- {p}" for p in parts) + "\n\n"


def build_tutor_chat_prompt(
    topic: str,
    user_message: str,
    *,
    history: list[dict[str, str]] | None = None,
    exam_context: dict[str, Any] | None = None,
    question_context: dict[str, Any] | None = None,
) -> tuple[str, str]:
    user_prompt = (
        f"Topic: {topic or 'general'}\n\n"
        f"{ADAPTIVE_TOPIC_RESTRICTION}\n\n"
        f"{format_exam_context(exam_context)}"
        f"{format_question_context(question_context)}"
        f"{format_conversation_history(history)}"
        f"User: {user_message}\n\n"
        f"{TUTOR_CHAT_RULES}\n\n"
        f"{TUTOR_CHAT_JSON_SCHEMA}\n\n"
        "Only answer questions related to this topic, the current exam, or the active question. "
        "If the student asks something unrelated to math or this topic, politely redirect them "
        "using a JSON object with a single step explaining the redirect.\n\n"
        "Now answer using the JSON schema only."
    )
    return TUTOR_CHAT_SYSTEM, user_prompt


# ---------------------------------------------------------------------------
# Tutor intro (legacy: tutor_intro) — lesson opener before practice
# ---------------------------------------------------------------------------

TUTOR_INTRO_SYSTEM = (
    f"You are {EXAMIQ_PERSONA}, a concise and friendly tutor.\n"
    "Plain text only — no markdown fences or fancy symbols."
)


def build_tutor_intro_prompt(topic: str) -> tuple[str, str]:
    user_prompt = f"""\
Provide a SHORT structured lesson intro for the topic: {topic}

FORMAT STRICTLY LIKE THIS:
Topic: <topic>

Lesson:
- 2 to 4 bullets of quick refresher concepts

Example:
A simple computation or example problem with solution.

Keep everything SHORT and easy to read."""
    return TUTOR_INTRO_SYSTEM, user_prompt


# ---------------------------------------------------------------------------
# Tutor Q&A (legacy: tutorQA) — lightweight single-shot help
# ---------------------------------------------------------------------------

TUTOR_QA_SYSTEM = (
    f"You are {EXAMIQ_PERSONA}, a helpful and clear tutor.\n"
    f"{MATH_NOTATION_RULES}"
)


def build_tutor_qa_prompt(topic: str, question: str) -> tuple[str, str]:
    user_prompt = (
        f"Topic: {topic}\n"
        f"Student question: {question}\n\n"
        "Provide a correct, step-by-step explanation.\n"
        "If conceptual, give a simple explanation with one example.\n"
        "If a calculation, solve it clearly."
    )
    return TUTOR_QA_SYSTEM, user_prompt


# ---------------------------------------------------------------------------
# Adaptive per-answer feedback (legacy: buildAdaptivePrompt) — during review
# ---------------------------------------------------------------------------

ADAPTIVE_FEEDBACK_SYSTEM = (
    f"You are {EXAMIQ_PERSONA}, an adaptive, friendly, and flexible tutor.\n"
    f"{MATH_NOTATION_RULES}\n{ADAPTIVE_TOPIC_RESTRICTION}\n"
    f"{CONFIDENCE_ADAPTIVE_RULES}\n"
    "Reply in plain sentences only — no JSON, no markdown code fences."
)


def build_adaptive_feedback_prompt(
    topic: str,
    question: str,
    user_answer: str,
    correct_answer: str,
    confidence: str = "medium",
    patterns: list[str] | None = None,
    question_type: str = "",
) -> tuple[str, str]:
    pattern_text = format_pattern_text(patterns)
    user_prompt = f"""\
### DYNAMIC FEEDBACK RULES
When the student is incorrect:
- In 3-5 sentences, explain what went wrong and why the correct approach works.
- Name the concept or rule they should remember; give a short hint toward the solution.
- You may reference the worked-solution steps, but still teach the idea here — do not say only "see the solution tab."
- If confidence is LOW, use simpler wording and smaller steps.

Use plain language. Avoid decorative symbols unless the question uses math notation.

### PERFORMANCE PATTERNS
{pattern_text}

Keep the whole reply under ~250 words. No long practice-recommendation blocks.

---

### STUDENT DATA
Topic: {topic}
Question Type: {question_type or "General"}
Question: {question}
Student Answer: {user_answer}
Correct Answer: {correct_answer}
Confidence Level: {confidence}

Tailor feedback to the question type (multiple choice, true/false, identification, enumeration, or numeric).

---

Generate adaptive feedback based on the rules above.
For MCQ mention the correct letter; for enumeration list required items; for true/false state True or False clearly.
Return only the feedback text — not JSON."""
    return ADAPTIVE_FEEDBACK_SYSTEM, user_prompt


# ---------------------------------------------------------------------------
# Post-exam AI feedback JSON (legacy: generateAIFeedbackPHP)
# ---------------------------------------------------------------------------

EXAM_FEEDBACK_SYSTEM = (
    f"You are {EXAMIQ_PERSONA}, an adaptive tutor focused on the student's weak areas.\n"
    f"{AI_FEEDBACK_JSON_RULES}"
)


def build_exam_feedback_batch_prompt(
    topic: str,
    items_text: str,
    patterns: list[str] | None = None,
) -> tuple[str, str, int]:
    pattern_text = format_pattern_text(patterns)
    user_prompt = (
        f"You are focused on the topic: {topic}.\n\n"
        "Below are incorrect answers the student made (only incorrect items). For each item:\n"
        "1. Explain clearly WHY the answer is wrong\n"
        "2. Provide the CORRECT ANSWER\n"
        "3. Show detailed step-by-step corrections (use actual line breaks, not \\\\n)\n"
        "4. Recommend 1-3 specific concepts to review and an ideal difficulty level\n\n"
        f"{AI_FEEDBACK_JSON_RULES}\n\n"
        f"Return ONLY a single JSON object with this structure:\n{AI_FEEDBACK_JSON_SCHEMA}\n\n"
        f"Here are the items to analyze (do not invent additional items):\n\n"
        f"{items_text}\nPatterns:\n{pattern_text}\n\n"
        "Follow the JSON schema exactly. Return ONLY the JSON object."
    )
    item_count = items_text.count("Item ")
    return EXAM_FEEDBACK_SYSTEM, user_prompt, exam_feedback_max_tokens(item_count)


def build_exam_feedback_single_prompt(
    topic: str,
    question: str,
    user_answer: str,
    correct_answer: str,
    confidence: str = "medium",
    patterns: list[str] | None = None,
) -> tuple[str, str, int]:
    pattern_text = format_pattern_text(patterns)
    user_prompt = (
        f"You are an adaptive tutor for topic: {topic}.\n\n"
        "Analyze the single student response below:\n"
        "- Explain clearly WHY the answer is wrong (if it is wrong)\n"
        "- Provide the CORRECT ANSWER\n"
        "- Show detailed step-by-step corrections (use actual line breaks in JSON, not \\\\n)\n"
        "- Recommend 1-3 specific concepts to review and an ideal difficulty (easy|medium|hard)\n\n"
        f"{AI_FEEDBACK_JSON_RULES}\n\n"
        f"Return ONLY a JSON object (no extra text) with this structure:\n{AI_FEEDBACK_JSON_SCHEMA}\n\n"
        f"Student data:\n"
        f"Question: {question}\n"
        f"Student Answer: {user_answer}\n"
        f"Correct Answer: {correct_answer}\n"
        f"Confidence: {confidence}\n"
        f"Patterns:\n{pattern_text}\n\n"
        "Follow the JSON schema exactly. Return ONLY the JSON object."
    )
    return EXAM_FEEDBACK_SYSTEM, user_prompt, exam_feedback_max_tokens(1)


def format_exam_feedback_item(
    index: int,
    *,
    question: str,
    user_answer: str,
    correct_answer: str,
    concept_tag: str | None = None,
    user_answer_text: str = "",
    correct_answer_text: str = "",
) -> str:
    """Format one incorrect item block for batch exam feedback (legacy itemsText)."""
    display_ua = user_answer
    if user_answer_text:
        display_ua = f"{user_answer} ({user_answer_text})"
    display_ca = correct_answer
    if correct_answer_text:
        display_ca = f"{correct_answer} ({correct_answer_text})"
    return (
        f"Item {index}:\n"
        f"Question: {question}\n"
        f"User Answer: {display_ua}\n"
        f"Correct Answer: {display_ca}\n"
        f"Concept Tag: {concept_tag or '(none)'}\n\n"
    )


# ---------------------------------------------------------------------------
# General tutor message (legacy: chatGPT non-adaptive branch)
# ---------------------------------------------------------------------------

GENERAL_TUTOR_SYSTEM = (
    f"You are {EXAMIQ_PERSONA}, a friendly and clear tutor. "
    "Your primary goal is to simplify concepts and show clear, step-by-step solutions.\n"
    f"{MATH_NOTATION_RULES}\n"
    "### RULES FOR TEXT CLARITY\n"
    "- Use **bolding** for final answers, key terms, and formula names.\n"
    "- Use *italic* for important warnings or concepts.\n"
    "- Use numbered lists or bullet points for steps.\n"
    f"{TUTOR_RESPONSE_STYLE}"
)


def build_general_tutor_prompt(user_message: str) -> tuple[str, str]:
    user_prompt = (
        f"User says: {user_message}\n\n"
        "Now respond clearly, strictly following all the rules above."
    )
    return GENERAL_TUTOR_SYSTEM, user_prompt


# ---------------------------------------------------------------------------
# Analytics / professor helpers (not in legacy PHP; kept for provider use)
# ---------------------------------------------------------------------------

def build_calibration_prompt(matrix: dict, weak_topics: list | None) -> str:
    return (
        f"Student calibration matrix: {json.dumps(matrix)}. "
        f"Weak topics: {weak_topics or []}. "
        "Write 2-3 sentences on over/under-confidence patterns and what to review."
    )


def build_course_report_prompt(course, summary: dict) -> str:
    return (
        f"Course {course.code} analytics: accuracy {summary['accuracy']}%, "
        f"misconception topics {summary.get('misconception_topics', [])}, "
        f"mistake patterns {summary.get('mistake_patterns', [])}. "
        "What should the professor review in class this week? 3-4 sentences."
    )


def build_difficulty_tag_prompt(stem: str) -> tuple[str, str]:
    system = "Reply with only easy, medium, or hard."
    user = (
        "Rate this exam question difficulty as exactly one of: easy, medium, hard.\n"
        f"Question: {stem}\n"
        "Reply with only the single word."
    )
    return system, user


# ---------------------------------------------------------------------------
# Topic / branch detection from uploaded learning material
# ---------------------------------------------------------------------------

TOPIC_DETECTION_SYSTEM = (
    f"You are {EXAMIQ_PERSONA} curriculum analyst for secondary mathematics education. "
    "Return valid JSON only. No markdown fences."
)

TOPIC_DETECTION_JSON_SCHEMA = (
    '{"detected_topics": ["Algebra", "Functions"], '
    '"matched_topic_id": 12, '
    '"matched_topic_name": "Algebra", '
    '"suggested_new_topics": ["Quadratic Equations"]}'
)


def build_topic_detection_prompt(
    source_material: str,
    existing_topics: list[dict[str, Any]],
) -> tuple[str, str]:
    """Return (system, user) prompts for detecting math topics in a module."""
    topics_payload = json.dumps(
        [{"id": t.get("id"), "name": t.get("name")} for t in existing_topics]
    )
    excerpt = (source_material or "").strip()
    if len(excerpt) > 12000:
        excerpt = excerpt[:12000] + "\n…[truncated]"
    user = (
        "Analyze this secondary mathematics learning module.\n"
        "Identify the main math topics or branches covered "
        "(e.g. Algebra, Geometry, Trigonometry, Functions, Statistics).\n"
        "Match to the best existing topic when possible "
        "(set matched_topic_id to that id, or null if none fit).\n"
        "List suggested_new_topics for clear themes not in the existing list.\n\n"
        f"Existing topics JSON:\n{topics_payload}\n\n"
        f"Module text:\n{excerpt}\n\n"
        f"Return JSON only matching:\n{TOPIC_DETECTION_JSON_SCHEMA}"
    )
    return TOPIC_DETECTION_SYSTEM, user


# ---------------------------------------------------------------------------
# Subject relevance for uploaded learning material
# ---------------------------------------------------------------------------

SUBJECT_RELEVANCE_SYSTEM = (
    f"You are {EXAMIQ_PERSONA} curriculum analyst for secondary mathematics education. "
    "Return valid JSON only. No markdown fences.\n"
    "Be strict: the module's PRIMARY focus must match the named course subject. "
    "Reject adjacent or sibling math subjects (e.g. history of mathematics, "
    "number systems, or algebra for a plane-and-solid-geometry course). "
    "A brief mention of the subject inside an otherwise unrelated document is "
    "NOT enough — set related=false."
)

SUBJECT_RELEVANCE_JSON_SCHEMA = (
    '{"related": true, '
    '"matched_topic_id": 12, '
    '"reason": "Covers right-triangle trigonometry."}'
)


def build_subject_relevance_prompt(
    source_material: str,
    subject_code: str,
    subject_name: str,
    topics: list[dict[str, Any]],
) -> tuple[str, str]:
    """Return (system, user) prompts for judging module-to-subject relevance.

    The model decides whether the module belongs to the course subject and which
    existing topic it best matches, so relevance works even when the subject
    code never literally appears in the extracted text.
    """
    topics_payload = json.dumps([{"id": t.get("id"), "name": t.get("name")} for t in topics])
    excerpt = (source_material or "").strip()
    if len(excerpt) > 12000:
        excerpt = excerpt[:12000] + "\n…[truncated]"
    user = (
        "A faculty member uploaded a learning module to generate exam questions for "
        f"the course subject {subject_code or '—'} — {subject_name or 'unknown'}.\n"
        "Decide whether the module's PRIMARY content is this subject.\n"
        "Reject if the document is mainly about a different math area "
        "(history of math, number systems, algebra, statistics, etc.) even if "
        "it briefly mentions this subject.\n"
        "Accept only when a substantial portion teaches this subject's skills "
        "or concepts (not merely references them historically).\n"
        "If related, set matched_topic_id to the best matching existing topic id "
        "(or null if none fit).\n"
        "Keep reason to one short sentence.\n\n"
        f"Existing topics JSON:\n{topics_payload}\n\n"
        f"Module text excerpt:\n{excerpt}\n\n"
        f"Return JSON only matching:\n{SUBJECT_RELEVANCE_JSON_SCHEMA}"
    )
    return SUBJECT_RELEVANCE_SYSTEM, user


def build_question_subject_relevance_prompt(
    stem: str,
    subject_code: str,
    subject_name: str,
    topic_name: str = "",
) -> tuple[str, str]:
    """Return (system, user) for judging a single question stem against a subject."""
    topic_line = f"Topic: {topic_name}\n" if topic_name else ""
    user = (
        "A faculty member is adding an exam question for the course subject "
        f"{subject_code or '—'} — {subject_name or 'unknown'}.\n"
        f"{topic_line}"
        f"Question stem:\n{stem.strip()}\n\n"
        "Decide whether this question belongs to this subject (not a different course). "
        "Reject pop culture, poetry, unrelated domains, or stems outside this subject.\n"
        "If related=false, reason MUST name the subject code and explain why it does not fit.\n"
        f"Return JSON only matching:\n{SUBJECT_RELEVANCE_JSON_SCHEMA}"
    )
    return SUBJECT_RELEVANCE_SYSTEM, user
