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


def mistake_student_threshold() -> int:
    """Distinct students who must miss a question before revision is urged."""
    from django.conf import settings

    return int(getattr(settings, "QUESTION_MISTAKE_STUDENT_THRESHOLD", 15) or 15)


def distinct_student_mistake_count(question) -> int:
    """Count unique students with at least one MistakeRecord for this question."""
    return question.mistake_records.values("student_id").distinct().count()


def question_needs_revision(question) -> bool:
    """True when enough distinct students have missed this question."""
    return distinct_student_mistake_count(question) >= mistake_student_threshold()


def question_feedback_summary(question, *, sample_limit: int = 5) -> dict:
    """Aggregate mistake stats and sample student AI feedback for faculty review."""
    from apps.ai.normalize import normalize_feedback_text

    records = list(
        question.mistake_records.exclude(ai_feedback="")
        .order_by("-occurred_at")
        .only("ai_feedback", "student_id", "occurred_at")[:40]
    )
    samples: list[dict] = []
    seen: set[str] = set()
    for record in records:
        text = normalize_feedback_text(record.ai_feedback or "")
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        samples.append({"text": text, "occurred_at": record.occurred_at})
        if len(samples) >= sample_limit:
            break

    unique_students = distinct_student_mistake_count(question)
    total_mistakes = question.mistake_records.count()
    threshold = mistake_student_threshold()
    return {
        "unique_students": unique_students,
        "total_mistakes": total_mistakes,
        "threshold": threshold,
        "needs_revision": unique_students >= threshold,
        "sample_feedback": samples,
    }


ADAPTIVE_EXPLANATION_FIELD_KEYS = (
    "what_went_wrong",
    "why",
    "quick_check",
    "remember",
    "worked_example",
)


def adaptive_explanation_has_content(data: dict | None) -> bool:
    """True when any curated adaptive-explanation field is non-empty."""
    if not isinstance(data, dict):
        return False
    return any(str(data.get(key) or "").strip() for key in ADAPTIVE_EXPLANATION_FIELD_KEYS)


def clean_adaptive_explanation(data: dict | None) -> dict:
    """Normalize faculty adaptive-explanation POST/JSON into a storage dict."""
    source = data if isinstance(data, dict) else {}
    cleaned: dict[str, str] = {}
    for key in ADAPTIVE_EXPLANATION_FIELD_KEYS:
        value = str(source.get(key) or "").strip()
        cleaned[key] = value
    return cleaned


def adaptive_explanation_from_post(post) -> dict:
    """Build adaptive_explanation JSON from form POST fields."""
    return clean_adaptive_explanation(
        {key: post.get(f"adaptive_{key}", "") for key in ADAPTIVE_EXPLANATION_FIELD_KEYS}
    )


def prefill_adaptive_explanation(question) -> dict:
    """Prefill edit form from saved JSON, else latest mistake AI feedback."""
    stored = clean_adaptive_explanation(getattr(question, "adaptive_explanation", None))
    if adaptive_explanation_has_content(stored):
        return stored

    from apps.ai.normalize import parse_adaptive_feedback

    for raw in question.mistake_records.exclude(ai_feedback="").order_by(
        "-occurred_at"
    ).values_list("ai_feedback", flat=True)[:10]:
        parsed = parse_adaptive_feedback(raw)
        if not parsed:
            continue
        filled = clean_adaptive_explanation(parsed)
        worked = parsed.get("quick_check")
        if worked and not filled.get("worked_example"):
            filled["worked_example"] = str(worked).strip()
        if adaptive_explanation_has_content(filled):
            return filled
    return clean_adaptive_explanation({})


def faculty_adaptive_feedback_json(question) -> str:
    """Serialize faculty adaptive_explanation for student feedback serving."""
    from apps.ai.normalize import adaptive_feedback_to_json, parse_adaptive_feedback

    data = clean_adaptive_explanation(getattr(question, "adaptive_explanation", None))
    if not adaptive_explanation_has_content(data):
        return ""

    payload = {
        "what_went_wrong": data.get("what_went_wrong") or "",
        "why": data.get("why") or "",
        "quick_check": data.get("quick_check") or data.get("worked_example") or None,
        "remember": data.get("remember") or "",
        "follow_ups": [],
        "solution_steps": None,
    }
    if data.get("worked_example") and not payload["quick_check"]:
        payload["quick_check"] = data["worked_example"]

    # Prefer validated shape when possible; otherwise store curated fields as-is.
    parsed = parse_adaptive_feedback(payload)
    if parsed:
        if data.get("worked_example"):
            parsed["worked_example"] = data["worked_example"]
        return adaptive_feedback_to_json(parsed)

    import json

    if data.get("worked_example"):
        payload["worked_example"] = data["worked_example"]
    return json.dumps(payload, ensure_ascii=False)

