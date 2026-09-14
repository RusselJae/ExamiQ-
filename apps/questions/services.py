from decimal import Decimal

from typing import TYPE_CHECKING



from django.db.models import QuerySet

from django.utils import timezone



if TYPE_CHECKING:

    from apps.questions.models import Question, QuestionChoice





def get_questions_for_session(
    topic,
    difficulty: str,
    count: int = 10,
    exclude_ids: list[int] | None = None,
) -> QuerySet:
    """Return random approved active questions for a review session."""
    from apps.questions.models import Question

    qs = Question.objects.filter(
        topic=topic,
        difficulty=difficulty,
        is_active=True,
        status=Question.Status.APPROVED,
    ).prefetch_related("choices", "explanation_steps")

    if exclude_ids:
        qs = qs.exclude(pk__in=exclude_ids)

    return qs.order_by("?")[:count]


def count_available_questions(
    topic, difficulty: str, *, question_type: str | None = None
) -> int:
    """Count approved active questions for a topic and difficulty."""
    from apps.questions.models import Question

    qs = Question.objects.filter(
        topic=topic,
        difficulty=difficulty,
        is_active=True,
        status=Question.Status.APPROVED,
    )
    if question_type:
        qs = qs.filter(question_type=question_type)
    return qs.count()


def count_available_questions_for_subject(
    subject,
    difficulty: str,
    *,
    question_type: str | None = None,
    question_types: list[str] | None = None,
) -> int:
    """Count approved active questions under all topics of a subject."""
    from apps.questions.models import Question

    types = list(question_types or [])
    if question_type:
        types = [question_type]
    qs = Question.objects.filter(
        topic__subject=subject,
        difficulty=difficulty,
        is_active=True,
        status=Question.Status.APPROVED,
    )
    if types:
        qs = qs.filter(question_type__in=types)
    return qs.count()


def question_ids_for_subject(
    subject,
    difficulty: str,
    *,
    limit: int = 10,
    question_type: str | None = None,
    question_types: list[str] | None = None,
) -> list[int]:
    """Sample up to ``limit`` approved question PKs for a subject at difficulty."""
    import random

    from apps.questions.models import Question

    types = list(question_types or [])
    if question_type:
        types = [question_type]
    qs = Question.objects.filter(
        topic__subject=subject,
        difficulty=difficulty,
        is_active=True,
        status=Question.Status.APPROVED,
    )
    if types:
        qs = qs.filter(question_type__in=types)
    ids = list(qs.values_list("pk", flat=True))
    if not ids:
        return []
    if len(ids) <= limit:
        random.shuffle(ids)
        return ids
    return random.sample(ids, limit)


def get_adaptive_questions_for_session(
    student,
    topic,
    difficulty: str,
    count: int = 1,
    exclude_ids: list[int] | None = None,
) -> QuerySet:
    """Return weighted-random questions prioritizing weak areas."""
    import random

    from django.db.models import Case, IntegerField, When

    from apps.analytics.models import MistakeRecord
    from apps.questions.models import Question
    from apps.reviews.models import Answer

    qs = Question.objects.filter(
        topic=topic,
        difficulty=difficulty,
        is_active=True,
        status=Question.Status.APPROVED,
    )
    if exclude_ids:
        qs = qs.exclude(pk__in=exclude_ids)

    if random.random() < 0.1:
        return qs.prefetch_related("choices", "explanation_steps").order_by("?")[:count]

    questions = list(qs.prefetch_related("choices", "explanation_steps"))
    if not questions:
        return Question.objects.none()

    mistake_topic_ids = set(
        MistakeRecord.objects.filter(student=student).values_list("topic_id", flat=True)
    )
    high_conf_wrong_q_ids = set(
        Answer.objects.filter(
            session__student=student,
            is_correct=False,
            confidence__gte=4,
        ).values_list("question_id", flat=True)
    )
    seen_q_ids = set(
        Answer.objects.filter(session__student=student).values_list("question_id", flat=True)
    )

    pool: list[tuple] = []
    for question in questions:
        weight = 0
        if question.topic_id in mistake_topic_ids:
            weight += 3
        if question.pk in high_conf_wrong_q_ids:
            weight += 2
        if question.pk not in seen_q_ids:
            weight += 1
        pool.append((question, max(weight, 1)))

    selected = []
    for _ in range(min(count, len(pool))):
        total = sum(weight for _, weight in pool)
        pick = random.uniform(0, total)
        cumulative = 0.0
        for index, (question, weight) in enumerate(pool):
            cumulative += weight
            if pick <= cumulative:
                selected.append(question)
                pool.pop(index)
                break

    if not selected:
        return Question.objects.none()

    ordering = Case(
        *[When(pk=q.pk, then=pos) for pos, q in enumerate(selected)],
        output_field=IntegerField(),
    )
    return (
        Question.objects.filter(pk__in=[q.pk for q in selected])
        .prefetch_related("choices", "explanation_steps")
        .order_by(ordering)
    )


def _normalize_text_answer(value: str | None) -> str:
    """Collapse whitespace and casefold for free-text comparison."""
    import re

    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def _normalize_true_false(value: str | None) -> str | None:
    text = (value or "").strip().casefold()
    if text in {"true", "t", "yes", "1"}:
        return "true"
    if text in {"false", "f", "no", "0"}:
        return "false"
    return None


def _split_enumeration_items(value: str | None) -> list[str]:
    import re

    parts = re.split(r"[\n|;]+", value or "")
    items = [_normalize_text_answer(part) for part in parts]
    return [item for item in items if item]


def grade_answer(
    question: "Question",
    submitted_value: str | None = None,
    selected_choice: "QuestionChoice | None" = None,
) -> tuple[bool, dict]:
    """Grade a student's answer.

    Returns (is_correct, context_dict).
    """
    from apps.questions.models import Question

    if question.question_type == Question.QuestionType.MCQ:
        is_correct = bool(selected_choice and selected_choice.is_correct)
        return is_correct, {
            "correct_choice": question.choices.filter(is_correct=True).first(),
            "selected_choice": selected_choice,
            "expected_answer": "",
            "submitted_value": submitted_value,
        }

    if question.question_type == Question.QuestionType.NUMERIC:
        try:
            submitted = Decimal(str(submitted_value).strip())
            correct = question.correct_answer
            tolerance = question.tolerance
            is_correct = abs(submitted - correct) <= tolerance
        except (ArithmeticError, AttributeError, TypeError, ValueError):
            is_correct = False
        return is_correct, {
            "correct_answer": question.correct_answer,
            "expected_answer": str(question.correct_answer or ""),
            "submitted_value": submitted_value,
        }

    if question.question_type == Question.QuestionType.TRUE_FALSE:
        expected = _normalize_true_false(question.expected_answer)
        submitted = _normalize_true_false(submitted_value)
        is_correct = bool(expected and submitted and expected == submitted)
        return is_correct, {
            "expected_answer": question.expected_answer,
            "submitted_value": submitted_value,
        }

    if question.question_type == Question.QuestionType.IDENTIFICATION:
        expected = _normalize_text_answer(question.expected_answer)
        submitted = _normalize_text_answer(submitted_value)
        is_correct = bool(expected and submitted and expected == submitted)
        return is_correct, {
            "expected_answer": question.expected_answer,
            "submitted_value": submitted_value,
        }

    if question.question_type == Question.QuestionType.ENUMERATION:
        expected_items = _split_enumeration_items(question.expected_answer)
        submitted_items = set(_split_enumeration_items(submitted_value))
        is_correct = bool(expected_items) and all(
            item in submitted_items for item in expected_items
        )
        return is_correct, {
            "expected_answer": question.expected_answer,
            "submitted_value": submitted_value,
            "expected_items": expected_items,
        }

    return False, {
        "expected_answer": getattr(question, "expected_answer", "") or "",
        "submitted_value": submitted_value,
    }





def submit_question_for_review(question: "Question", user) -> "Question":
    """Keep a draft/pending copy owned by the faculty author (no chairperson)."""
    from apps.questions.models import Question

    question.status = Question.Status.DRAFT
    question.proposed_by = user
    question.validated_by = None
    question.validated_at = None
    question.rejection_note = ""
    question.save(
        update_fields=[
            "status",
            "proposed_by",
            "validated_by",
            "validated_at",
            "rejection_note",
        ]
    )
    return question


def publish_question_as_faculty(
    question: "Question",
    faculty,
    *,
    approve_explanations: bool = True,
) -> "Question":
    """Faculty expert attestation: publish question for student exams."""
    from apps.questions.models import Question

    question.status = Question.Status.APPROVED
    question.is_active = True
    question.proposed_by = question.proposed_by or faculty
    question.validated_by = faculty
    question.validated_at = timezone.now()
    question.reviewed_by = faculty
    question.reviewed_at = timezone.now()
    question.rejection_note = ""
    if approve_explanations and question.explanation_steps.exists():
        question.explanation_status = "faculty_approved"
    update_fields = [
        "status",
        "is_active",
        "proposed_by",
        "validated_by",
        "validated_at",
        "reviewed_by",
        "reviewed_at",
        "rejection_note",
        "explanation_status",
    ]
    question.save(update_fields=update_fields)
    return question


def approve_question(question: "Question", reviewer) -> "Question":
    """Alias for faculty publish (legacy name kept for imports)."""
    return publish_question_as_faculty(question, reviewer)


def reject_question(question: "Question", reviewer, note: str = "") -> "Question":
    from apps.questions.models import Question

    question.status = Question.Status.DRAFT
    question.is_active = False
    question.reviewed_by = reviewer
    question.reviewed_at = timezone.now()
    question.validated_by = None
    question.validated_at = None
    question.explanation_status = "draft"
    question.rejection_note = note
    question.save(
        update_fields=[
            "status",
            "is_active",
            "reviewed_by",
            "reviewed_at",
            "validated_by",
            "validated_at",
            "explanation_status",
            "rejection_note",
        ]
    )
    return question


def count_bank_questions_for_subject(subject) -> int:
    """Count non-rejected questions counting toward the per-subject bank cap."""
    from apps.questions.models import Question

    return Question.objects.filter(
        topic__subject=subject,
    ).exclude(status=Question.Status.REJECTED).count()


def subject_bank_slots_remaining(subject) -> int:
    from django.conf import settings

    cap = getattr(settings, "MAX_QUESTIONS_PER_SUBJECT", 100)
    return max(0, cap - count_bank_questions_for_subject(subject))


def assert_subject_bank_has_capacity(subject, *, additional: int = 1) -> None:
    """Raise ValueError when adding ``additional`` questions would exceed the cap."""
    from django.conf import settings

    cap = getattr(settings, "MAX_QUESTIONS_PER_SUBJECT", 100)
    remaining = subject_bank_slots_remaining(subject)
    if additional > remaining:
        raise ValueError(
            f"This subject already has {count_bank_questions_for_subject(subject)} "
            f"questions (max {cap}). Free space or archive questions before adding more."
        )


def approve_question_explanations(question: "Question", faculty) -> "Question":
    question.explanation_status = "faculty_approved"
    question.validated_by = question.validated_by or faculty
    question.validated_at = question.validated_at or timezone.now()
    question.save(
        update_fields=["explanation_status", "validated_by", "validated_at"]
    )
    return question





def create_question(question_data: dict, choices_data: list[dict], steps_data: list[dict]) -> "Question":

    """Create a question with choices and explanation steps."""

    from apps.questions.models import ExplanationStep, Question, QuestionChoice



    question = Question.objects.create(**question_data)

    for choice in choices_data:

        if choice.get("text"):

            QuestionChoice.objects.create(question=question, **choice)

    for step in steps_data:

        if step.get("content"):

            ExplanationStep.objects.create(question=question, **step)

    return question





def update_question(

    question: "Question",

    question_data: dict,

    choices_data: list[dict],

    steps_data: list[dict],

) -> "Question":

    """Update a question and replace choices/steps."""

    from apps.questions.models import ExplanationStep, QuestionChoice



    for field, value in question_data.items():

        setattr(question, field, value)

    question.save()



    question.choices.all().delete()

    for choice in choices_data:

        if choice.get("text"):

            QuestionChoice.objects.create(question=question, **choice)



    question.explanation_steps.all().delete()

    for step in steps_data:

        if step.get("content"):

            ExplanationStep.objects.create(question=question, **step)

    return question





def activate_question(question: "Question") -> "Question":
    question.is_active = True
    question.save(update_fields=["is_active"])
    return question


def deactivate_question(question: "Question") -> "Question":

    question.is_active = False

    question.save(update_fields=["is_active"])

    return question


def normalize_stem(stem: str) -> str:
    """Normalize question stem for duplicate comparison."""
    import re

    text = (stem or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def find_duplicate_question(topic_id: int, stem: str, *, exclude_pk: int | None = None):
    """Return an existing question in the topic with the same normalized stem."""
    from apps.questions.models import Question

    normalized = normalize_stem(stem)
    if not normalized:
        return None
    for question in Question.objects.filter(topic_id=topic_id).only("pk", "stem"):
        if normalize_stem(question.stem) == normalized:
            if exclude_pk and question.pk == exclude_pk:
                continue
            return question
    return None


def build_steps_from_post(steps_raw: str, concept_tag: str = "", solution_summary: str = "") -> list[dict]:
    """Parse explanation steps from JSON POST field or fallbacks."""
    import json

    steps: list[dict] = []
    if steps_raw:
        try:
            parsed = json.loads(steps_raw)
            if isinstance(parsed, list):
                for index, content in enumerate(parsed, start=1):
                    text = str(content).strip()
                    if text:
                        steps.append({"order": index, "content": text})
        except (json.JSONDecodeError, TypeError):
            pass
    if not steps and solution_summary.strip():
        steps.append({"order": 1, "content": solution_summary.strip()})
    if not steps and concept_tag.strip():
        steps.append({"order": 1, "content": concept_tag.strip()})
    return steps

