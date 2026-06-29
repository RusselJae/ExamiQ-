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
- Keep explanations simple unless the user asks for detailed steps.
- If a problem needs more than three main steps, break work into numbered chunks.
- If calculation is requested: show clean step-by-step work.
- If conceptual: give a short definition plus one simple example.
- Friendly, supportive tone. If the user is confused, rephrase or use an analogy."""

TUTOR_CHAT_RULES = """\
RULES:
- Do NOT greet the user (no 'Hi', no 'Hello').
- Do NOT introduce yourself.
- Respond directly to the topic.
- Keep explanations simple unless the user asks for detailed steps.
- If the message is vague, connect it to the topic or the exam they just took.
- If it is about a calculation, show clean steps using plain text.
- If it is conceptual, explain with 1 example."""

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
    '"answer_correct": true/false, "feedback": "2-3 sentences", '
    '"suggested_concept_tag": "short label"}'
)

QUESTION_JSON_SCHEMA = (
    '[{"stem":"short question text","concept_tag":"2-4 word tag","correct_label":"B",'
    '"choices":[{"label":"A","text":"plausible distractor","is_correct":false},'
    '{"label":"B","text":"the one correct answer","is_correct":true},'
    '{"label":"C","text":"plausible distractor","is_correct":false},'
    '{"label":"D","text":"plausible distractor","is_correct":false}],'
    '"explanation_steps":["Step 1: ...","Step 2: ..."],'
    '"solution_summary":"Final answer: B because ..."}]'
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


def question_generation_max_tokens(count: int, difficulty: str = "") -> int:
    from django.conf import settings

    cap = getattr(settings, "GEMINI_QUESTION_MAX_OUTPUT_TOKENS", 2048)
    base = min(cap, max(800, 280 * count))
    if difficulty == Question.Difficulty.HARD:
        base = min(cap, int(base * 1.35))
    return base


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

QUESTION_GENERATION_SYSTEM = (
    f"You are {EXAMIQ_PERSONA} question writer. Return valid JSON only — no markdown, no prose.\n"
    "Rules:\n"
    "- MCQ with exactly 4 distinct non-empty choices (A-D); exactly one correct.\n"
    "- correct_label MUST match the single choice with is_correct:true.\n"
    "- Randomize correct_label per question (A, B, C, or D). Never default all answers to A.\n"
    "- In a batch, use at least 2 different correct_label values when count ≥ 2.\n"
    "- Stems ≤50 words; choice text ≤120 characters; difficulty must match requested level.\n"
    "- Distractors plausible but definitively wrong to a subject expert.\n"
    "- Solve each problem yourself before marking the answer; verify correctness.\n"
    "- For computation or multi-step problems: include ≥2 explanation_steps showing work.\n"
    "- solution_summary states the correct choice letter and why.\n"
    "- Match the subject field exactly (theory, math, programming, statistics, etc.).\n"
    "JSON output rules:\n"
    "- Return ONLY a raw JSON array. No markdown fences or commentary.\n"
    "- No trailing commas. Escape double quotes inside strings.\n"
    "Use plain text for formulas and code snippets — no LaTeX or markdown."
)


def _difficulty_guidance(difficulty: str) -> str:
    return DIFFICULTY_GUIDANCE.get(difficulty, DIFFICULTY_GUIDANCE["medium"])


def build_question_generation_prompt(
    topic,
    difficulty: str,
    count: int,
    reference_stem: str = "",
) -> tuple[str, str, int]:
    """Return (system_instruction, user_prompt, max_output_tokens)."""
    subject = topic.subject
    label = difficulty_label(difficulty)
    ref = reference_stem.strip() or "none"
    guidance = _difficulty_guidance(difficulty)

    user_prompt = (
        f"Generate exactly {count} multiple-choice questions.\n"
        f"Topic: {topic.name} | Subject: {subject.code} – {subject.name}\n"
        f"Difficulty: {label} ({difficulty})\n"
        f"{guidance}\n"
        f"Reference (optional): {ref}\n\n"
        "Keep stems and choice text short. Escape quotes inside JSON strings.\n"
        "Pick a different correct_label for each question when possible (mix A, B, C, D).\n"
        "Do NOT place the correct answer on the same letter for every question.\n"
        "Each question must include explanation_steps (≥1) and solution_summary.\n"
        f"JSON array schema (example shows B correct — use any letter per question):\n"
        f"{QUESTION_JSON_SCHEMA}"
    )
    return QUESTION_GENERATION_SYSTEM, user_prompt, question_generation_max_tokens(count, difficulty)


# ---------------------------------------------------------------------------
# Question validation (professor validate modal)
# ---------------------------------------------------------------------------

QUESTION_VALIDATION_SYSTEM = (
    f"You are {EXAMIQ_PERSONA} exam reviewer. Return valid JSON only.\n"
    "Structural checks: stem is clear; exactly 4 choices A-D with distinct text; "
    "exactly one marked correct; correct_label matches the true answer.\n"
    "Semantic checks: solve the problem independently; confirm topic and difficulty fit.\n"
    "Set is_valid:false if ANY check fails. Be strict — do not pass flawed questions."
)


def build_question_validation_prompt(
    stem: str,
    choices: list[dict],
    topic,
    difficulty: str,
    correct_label: str = "",
) -> tuple[str, str]:
    subject_name = topic.subject.name if topic and hasattr(topic, "subject") else ""
    topic_name = topic.name if topic else ""
    choices_text = json.dumps(choices)
    user_prompt = (
        f"Validate this MCQ for subject '{subject_name}', topic '{topic_name}', "
        f"difficulty '{difficulty}'.\n"
        f"Stem: {stem}\nChoices: {choices_text}\nMarked correct: {correct_label}\n\n"
        "Solve the problem yourself. Verify the marked choice is definitively correct.\n"
        "Reject if choices are duplicated, ambiguous, off-topic, or the marked answer is wrong.\n"
        f"Return JSON only:\n{QUESTION_VALIDATION_JSON_SCHEMA}"
    )
    return QUESTION_VALIDATION_SYSTEM, user_prompt


# ---------------------------------------------------------------------------
# Tutor chat (legacy: ai_chat) — future student tutor UI
# ---------------------------------------------------------------------------

TUTOR_CHAT_SYSTEM = (
    f"You are {EXAMIQ_PERSONA}, a clear and friendly tutor for math and computer science.\n"
    f"{MATH_NOTATION_RULES}\n{TUTOR_RESPONSE_STYLE}"
)


def build_tutor_chat_prompt(
    topic: str,
    user_message: str,
    *,
    history: list[dict[str, str]] | None = None,
    exam_context: dict[str, Any] | None = None,
) -> tuple[str, str]:
    user_prompt = (
        f"Topic: {topic or 'general'}\n\n"
        f"{format_exam_context(exam_context)}"
        f"{format_conversation_history(history)}"
        f"User: {user_message}\n\n"
        f"{TUTOR_CHAT_RULES}\n\n"
        "Now answer clearly and continue the conversation, using prior context where helpful."
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
    f"{CONFIDENCE_ADAPTIVE_RULES}\n{TUTOR_RESPONSE_STYLE}"
)


def build_adaptive_feedback_prompt(
    topic: str,
    question: str,
    user_answer: str,
    correct_answer: str,
    confidence: str = "medium",
    patterns: list[str] | None = None,
) -> tuple[str, str]:
    pattern_text = format_pattern_text(patterns)
    user_prompt = f"""\
### DYNAMIC FEEDBACK RULES
When the student is incorrect:
- Give numbered step-by-step solutions and explain their mistake clearly.
- If confidence is LOW, use simpler explanations.
- If confidence is HIGH, include deeper reasoning.

Use plain language. Avoid decorative symbols unless the question uses math notation.

### SKILL & PRACTICE RECOMMENDATION RULES
Include what to practice next, ideal difficulty, concepts needing attention, \
and a suggested number of practice questions.

### PERFORMANCE PATTERNS
{pattern_text}

Provide insights on repeated mistakes, confused concepts, and strengths/weaknesses.

---

### STUDENT DATA
Topic: {topic}
Question: {question}
Student Answer: {user_answer}
Correct Answer: {correct_answer}
Confidence Level: {confidence}

---

Now generate adaptive, personalized feedback based on all rules above."""
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
