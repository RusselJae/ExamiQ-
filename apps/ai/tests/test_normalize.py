import random

import pytest

from apps.ai.normalize import (
    normalize_feedback_text,
    normalize_generated_questions,
    randomize_choice_positions,
    reconcile_question_choices,
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


def test_normalize_strips_explanation_fields():
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
            "explanation_steps": ["Do not keep this."],
            "solution_summary": "Do not keep this either.",
        }
    ]
    result = normalize_generated_questions(questions, rng=random.Random(0))
    assert "explanation_steps" not in result[0]
    assert "solution_summary" not in result[0]


def test_normalize_identification_payload():
    result = normalize_generated_questions(
        [
            {
                "question_type": "identification",
                "stem": "Name the slope formula.",
                "concept_tag": "algebra",
                "expected_answer": "  Rise Over Run ",
            }
        ],
        question_type="identification",
    )
    assert result[0]["question_type"] == "identification"
    assert result[0]["expected_answer"] == "Rise Over Run"
    assert "choices" not in result[0]


def test_normalize_true_false_payload():
    result = normalize_generated_questions(
        [
            {
                "question_type": "true_false",
                "stem": "Zero is a natural number.",
                "expected_answer": "false",
            }
        ],
        question_type="true_false",
    )
    assert result[0]["expected_answer"] == "False"


def test_normalize_true_false_accepts_bool_json_values():
    result = normalize_generated_questions(
        [
            {
                "question_type": "true_false",
                "stem": "A triangle has three sides.",
                "expected_answer": True,
            },
            {
                "question_type": "true_false",
                "stem": "A triangle has four sides.",
                "expected_answer": False,
            },
        ],
        question_type="true_false",
    )
    assert result[0]["expected_answer"] == "True"
    assert result[1]["expected_answer"] == "False"


def test_normalize_enumeration_accepts_list_json_values():
    result = normalize_generated_questions(
        [
            {
                "question_type": "enumeration",
                "stem": "List central tendency measures.",
                "expected_answer": ["mean", "median", "mode"],
            }
        ],
        question_type="enumeration",
    )
    assert result[0]["expected_answer"] == "mean\nmedian\nmode"


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
