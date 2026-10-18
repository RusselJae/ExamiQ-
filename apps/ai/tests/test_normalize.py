import random

import pytest

from apps.ai.normalize import (
    normalize_feedback_text,
    normalize_generated_questions,
    randomize_choice_positions,
    reconcile_question_choices,
    validate_concept_practice_question,
    validate_concept_remediation,
)


@pytest.mark.parametrize("label", ["B", "C", "D"])
def test_reconcile_question_choices_sets_single_correct(label):
    question = reconcile_question_choices({
        "stem": "Test?",
        "correct_label": label,
        "choices": [
            {"label": "A", "text": "one", "is_correct": True},
            {"label": "B", "text": "two", "is_correct": False},
            {"label": "C", "text": "three", "is_correct": False},
            {"label": "D", "text": "four", "is_correct": False},
        ],
    })
    correct = [c for c in question["choices"] if c["is_correct"]]
    assert len(correct) == 1
    assert correct[0]["label"] == label


def test_randomize_moves_correct_text_to_new_slot():
    source = {
        "stem": "Which is true?",
        "correct_label": "A",
        "choices": [
            {"label": "A", "text": "correct answer", "is_correct": True},
            {"label": "B", "text": "wrong 1", "is_correct": False},
            {"label": "C", "text": "wrong 2", "is_correct": False},
            {"label": "D", "text": "wrong 3", "is_correct": False},
        ],
    }
    result = randomize_choice_positions(source, random.Random(0))
    correct = next(c for c in result["choices"] if c["is_correct"])
    assert correct["text"] == "correct answer"
    assert result["correct_label"] == correct["label"]


def test_normalize_varies_batch_positions():
    questions = [
        {
            "stem": "Q1",
            "correct_label": "A",
            "choices": [
                {"label": "A", "text": "right", "is_correct": True},
                {"label": "B", "text": "w1", "is_correct": False},
                {"label": "C", "text": "w2", "is_correct": False},
                {"label": "D", "text": "w3", "is_correct": False},
            ],
        },
        {
            "stem": "Q2",
            "correct_label": "A",
            "choices": [
                {"label": "A", "text": "right2", "is_correct": True},
                {"label": "B", "text": "w4", "is_correct": False},
                {"label": "C", "text": "w5", "is_correct": False},
                {"label": "D", "text": "w6", "is_correct": False},
            ],
        },
        {
            "stem": "Q3",
            "correct_label": "A",
            "choices": [
                {"label": "A", "text": "right3", "is_correct": True},
                {"label": "B", "text": "w7", "is_correct": False},
                {"label": "C", "text": "w8", "is_correct": False},
                {"label": "D", "text": "w9", "is_correct": False},
            ],
        },
    ]
    result = normalize_generated_questions(questions, rng=random.Random(1))
    labels = [q["correct_label"] for q in result]
    assert len(set(labels)) > 1


def test_normalize_keeps_explanation_fields():
    questions = [
        {
            "stem": "Q1",
            "correct_label": "B",
            "choices": [
                {"label": "A", "text": "w1", "is_correct": False},
                {"label": "B", "text": "right", "is_correct": True},
                {"label": "C", "text": "w2", "is_correct": False},
                {"label": "D", "text": "w3", "is_correct": False},
            ],
            "explanation_steps": [" Keep this step. ", "", "And this one."],
            "solution_summary": " Final answer: B ",
            "what_went_wrong": " Missed a condition. ",
            "why": " The rule applies. ",
            "quick_check": " Check B. ",
            "remember": " Condition first. ",
            "worked_example": " Example here. ",
        }
    ]
    result = normalize_generated_questions(questions, rng=random.Random(0))
    assert result[0]["explanation_steps"] == ["Keep this step.", "And this one."]
    assert result[0]["solution_summary"] == "Final answer: B"
    assert result[0]["what_went_wrong"] == "Missed a condition."
    assert result[0]["why"] == "The rule applies."
    assert result[0]["quick_check"] == "Check B."
    assert result[0]["remember"] == "Condition first."
    assert result[0]["worked_example"] == "Example here."


def test_normalize_non_mcq_payload_coerces_to_mcq():
    result = normalize_generated_questions(
        [
            {
                "question_type": "identification",
                "stem": "Name the slope formula.",
                "concept_tag": "algebra",
                "expected_answer": "  Rise Over Run ",
                "choices": [
                    {"label": "A", "text": "rise/run", "is_correct": True},
                    {"label": "B", "text": "run/rise", "is_correct": False},
                    {"label": "C", "text": "x/y", "is_correct": False},
                    {"label": "D", "text": "y/x", "is_correct": False},
                ],
                "correct_label": "A",
            }
        ],
        question_type="identification",
    )
    assert result[0]["question_type"] == "mcq"


def test_normalize_true_false_request_coerces_to_mcq():
    result = normalize_generated_questions(
        [
            {
                "question_type": "true_false",
                "stem": "Zero is a natural number.",
                "expected_answer": "false",
                "choices": [
                    {"label": "A", "text": "True", "is_correct": False},
                    {"label": "B", "text": "False", "is_correct": True},
                    {"label": "C", "text": "Sometimes", "is_correct": False},
                    {"label": "D", "text": "Undefined", "is_correct": False},
                ],
                "correct_label": "B",
            }
        ],
        question_type="true_false",
    )
    assert result[0]["question_type"] == "mcq"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Plain feedback text.", "Plain feedback text."),
        (
            '```json\n{"feedback": "That is the wrong approach."}\n```',
            "That is the wrong approach.",
        ),
        ('{"feedback": "Check the distance formula."}', "Check the distance formula."),
        ('{"why_wrong": "You forgot to simplify."}', "You forgot to simplify."),
    ],
)
def test_normalize_feedback_text_strips_json(raw, expected):
    assert normalize_feedback_text(raw) == expected


def test_normalize_feedback_text_strips_internal_meta_prefix():
    assert (
        normalize_feedback_text("Redirect: Let's focus on the current problem.")
        == "Let's focus on the current problem."
    )
    assert (
        normalize_feedback_text("Query: How do I factor this?")
        == "How do I factor this?"
    )


def test_validate_adaptive_feedback_accepts_good_payload():
    from apps.ai.normalize import validate_adaptive_feedback

    raw = {
        "what_went_wrong": "'Non-singular' needs det ≠ 0. Here det = 0.",
        "why": "Inverse divides by det(A), so det 0 means no inverse.",
        "quick_check": "[[1,2],[2,4]] has det 0, so singular.",
        "remember": "Singular = det 0 = no inverse.",
        "follow_ups": ["Why dependent rows?", "Try 3×3", "Quiz me"],
        "solution_steps": None,
    }
    validated = validate_adaptive_feedback(raw)
    assert validated is not None
    assert validated["quick_check"]
    assert validated["solution_steps"] is None
    assert len(validated["follow_ups"]) == 3


def test_validate_adaptive_feedback_accepts_solution_steps_with_step_labels():
    from apps.ai.normalize import validate_adaptive_feedback

    raw = {
        "what_went_wrong": "You used the sum instead of the product rule.",
        "why": "The derivative of uv is u'v + uv', not u' + v'.",
        "quick_check": None,
        "remember": "Product rule: u'v + uv'.",
        "follow_ups": ["Show me product rule", "Try another"],
        "solution_steps": [
            "Step 1. Identify u = x^2 and v = sin(x).",
            "Step 2. Compute u' = 2x and v' = cos(x).",
            "Step 3. Combine: 2x sin(x) + x^2 cos(x).",
        ],
    }
    validated = validate_adaptive_feedback(raw)
    assert validated is not None
    assert len(validated["solution_steps"]) == 3
    assert "Step 1" in validated["solution_steps"][0]


def test_validate_adaptive_feedback_rejects_filler_and_steps():
    from apps.ai.normalize import validate_adaptive_feedback

    bad = {
        "what_went_wrong": "Great try — double-check your work next time.",
        "why": "Step 1. The answer is D.",
        "quick_check": None,
        "remember": "Since you have high confidence slow down a lot more please now",
        "follow_ups": ["ok"],
    }
    assert validate_adaptive_feedback(bad) is None


def test_validate_correct_adaptive_feedback_accepts_good_payload():
    from apps.ai.normalize import validate_correct_adaptive_feedback

    raw = {
        "why_it_works": "Inverse divides by det(A), so det 0 means singular.",
        "remember": "Singular = det 0 = no inverse.",
        "worked_example": "[[1,2],[2,4]] has det 0, so singular.",
        "follow_ups": ["Why dependent rows?", "Try 3×3", "Quiz me"],
    }
    validated = validate_correct_adaptive_feedback(raw)
    assert validated is not None
    assert validated["kind"] == "correct"
    assert validated["worked_example"]
    assert len(validated["follow_ups"]) == 3


def test_validate_correct_adaptive_feedback_allows_null_example():
    from apps.ai.normalize import validate_correct_adaptive_feedback

    raw = {
        "why_it_works": "Det 0 means no inverse exists for the matrix.",
        "remember": "Singular = det 0 = no inverse.",
        "worked_example": None,
        "follow_ups": ["Why dependent rows?"],
    }
    validated = validate_correct_adaptive_feedback(raw)
    assert validated is not None
    assert validated["worked_example"] is None


def test_parse_any_prefers_correct_schema():
    from apps.ai.normalize import parse_any_adaptive_feedback

    raw = {
        "why_it_works": "Det 0 blocks the inverse formula.",
        "remember": "Singular = det 0 = no inverse.",
        "worked_example": None,
        "follow_ups": ["Quiz me"],
    }
    parsed = parse_any_adaptive_feedback(raw)
    assert parsed["kind"] == "correct"
    assert "why_it_works" in parsed


def test_normalize_feedback_prefers_structured_fields():
    raw = (
        '{"what_went_wrong": "Chose non-singular.", '
        '"why": "Det 0 means singular.", '
        '"quick_check": null, '
        '"remember": "Det 0 = singular.", '
        '"follow_ups": ["a", "b", "c"]}'
    )
    text = normalize_feedback_text(raw)
    assert "Chose non-singular" in text
    assert "Det 0 means singular" in text


def _valid_remediation() -> dict:
    return {
        "diagnosis": {
            "type": "misconception",
            "what_went_wrong": "You chose x=11, which usually means you added instead of subtracting.",
            "prerequisite_flag": None,
        },
        "explanation": {
            "style_used": "worked_example",
            "core_idea": "Undo operations in reverse order.",
            "key_rules": ["Undo +/- first", "Then divide"],
        },
        "worked_example": {
            "problem": "Solve $3x+5=20$",
            "steps": [
                {"step": "Subtract 5", "why": "Undo addition"},
                {"step": "Divide by 3", "why": "Undo multiply"},
            ],
            "final_answer": "$x=5$",
        },
        "common_mistakes": [
            {
                "mistake": "Add instead of subtract",
                "why_it_fails": "Moves constant the wrong way",
                "fix": "Use the opposite operation",
            }
        ],
        "try_it": {
            "problem": "Solve $4x+9=33$. First step?",
            "first_step_choices": [
                "Divide by 4",
                "Add 9",
                "Subtract 9",
            ],
            "correct_index": 2,
            "hint": "Undo the constant first.",
            "feedback_if_wrong": "To undo +9, subtract 9.",
        },
        "check_yourself": "Substitute back into the original equation.",
    }


def test_validate_concept_remediation_accepts_valid():
    assert validate_concept_remediation(_valid_remediation()) is not None


def test_validate_concept_remediation_rejects_bad_try_it_count():
    data = _valid_remediation()
    data["try_it"]["first_step_choices"] = ["Only one"]
    assert validate_concept_remediation(data) is None


def _valid_practice() -> dict:
    return {
        "concept": "Two-step equations",
        "difficulty": "beginner",
        "question": "Solve $2x+3=11$. What is $x$?",
        "options": [
            {
                "id": "A",
                "text": "8",
                "is_correct": False,
                "error_tag": "forgot_to_divide",
                "why_wrong": "Subtracted but did not divide.",
            },
            {
                "id": "B",
                "text": "4",
                "is_correct": True,
                "error_tag": None,
                "why_wrong": None,
            },
            {
                "id": "C",
                "text": "7",
                "is_correct": False,
                "error_tag": "sign_error",
                "why_wrong": "Added instead of subtracting.",
            },
            {
                "id": "D",
                "text": "14",
                "is_correct": False,
                "error_tag": "wrong_operation_order",
                "why_wrong": "Divided before undoing the constant.",
            },
        ],
        "hint": "Undo +3 first.",
        "solution_steps": ["Subtract 3", "Divide by 2", "Check"],
        "final_answer": "$x=4$",
        "self_check": "Plug x=4 back into 2x+3.",
    }


def test_validate_concept_practice_accepts_valid():
    assert validate_concept_practice_question(_valid_practice()) is not None


def test_validate_concept_practice_rejects_two_corrects():
    data = _valid_practice()
    data["options"][0]["is_correct"] = True
    assert validate_concept_practice_question(data) is None


def test_validate_concept_practice_rejects_duplicate_texts():
    data = _valid_practice()
    data["options"][2]["text"] = data["options"][1]["text"]
    assert validate_concept_practice_question(data) is None
