import random

import pytest

from apps.ai.normalize import (
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
