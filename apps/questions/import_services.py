"""CSV import helpers for bulk question creation."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from apps.questions.models import Question, Subject, Topic
from apps.questions.services import (
    create_question,
    find_duplicate_question,
    normalize_stem,
)
from apps.questions.validation import validate_question_for_submit

EXPECTED_HEADERS = {
    "subject_code",
    "topic_name",
    "difficulty",
    "question_type",
    "stem",
}

VALID_TYPES = {
    Question.QuestionType.MCQ,
    Question.QuestionType.TRUE_FALSE,
    Question.QuestionType.IDENTIFICATION,
    Question.QuestionType.ENUMERATION,
}

VALID_DIFFICULTIES = {c.value for c in Question.Difficulty}
VALID_STATUSES = {c.value for c in Question.Status}


class ImportFormatError(ValueError):
    """Raised when the uploaded file cannot be parsed as a question CSV."""


@dataclass
class ImportRowError:
    row_number: int
    stem: str
    message: str


@dataclass
class ImportSummary:
    created: int = 0
    skipped_invalid: int = 0
    skipped_duplicates: int = 0
    row_errors: list[ImportRowError] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "created": self.created,
            "skipped_invalid": self.skipped_invalid,
            "skipped_duplicates": self.skipped_duplicates,
            "errors": [
                {
                    "row": err.row_number,
                    "stem": err.stem,
                    "message": err.message,
                }
                for err in self.row_errors
            ],
        }


def _normalize_header(name: str) -> str:
    return (name or "").strip().lower().lstrip("\ufeff")


def _coerce_cell(value: str | None) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if "\\n" in text:
        text = text.replace("\\n", "\n")
    return text


def _normalize_row(raw: dict[str, str | None]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in raw.items():
        header = _normalize_header(key)
        if not header:
            continue
        normalized[header] = _coerce_cell(value)
    return normalized


def _parse_bool(value: str, *, default: bool = True) -> bool:
    token = (value or "").strip().casefold()
    if not token:
        return default
    if token in {"true", "1", "yes", "y"}:
        return True
    if token in {"false", "0", "no", "n"}:
        return False
    return default


def _normalize_question_type(value: str) -> str:
    token = (value or "").strip().casefold().replace(" ", "_").replace("-", "_")
    aliases = {
        "multiple_choice": Question.QuestionType.MCQ,
        "mcq": Question.QuestionType.MCQ,
        "true_false": Question.QuestionType.TRUE_FALSE,
        "true_or_false": Question.QuestionType.TRUE_FALSE,
        "tf": Question.QuestionType.TRUE_FALSE,
        "identification": Question.QuestionType.IDENTIFICATION,
        "enumeration": Question.QuestionType.ENUMERATION,
    }
    return aliases.get(token, token)


def _normalize_difficulty(value: str) -> str:
    token = (value or "").strip().casefold()
    aliases = {
        "beginner": Question.Difficulty.EASY,
        "easy": Question.Difficulty.EASY,
        "intermediate": Question.Difficulty.MEDIUM,
        "medium": Question.Difficulty.MEDIUM,
        "advanced": Question.Difficulty.HARD,
        "hard": Question.Difficulty.HARD,
    }
    return aliases.get(token, token)


def _codes_match(left: str, right: str) -> bool:
    return left.strip().casefold() == right.strip().casefold()


def _read_csv_rows(uploaded_file) -> list[dict[str, str]]:
    """Parse CSV bytes into normalized row dicts."""
    raw_bytes = uploaded_file.read()
    if isinstance(raw_bytes, str):
        raw_bytes = raw_bytes.encode("utf-8")
    if not raw_bytes.strip():
        raise ImportFormatError("The CSV file is empty.")

    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            text = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            text = None
    if text is None:
        raise ImportFormatError(
            "Could not read the CSV file. Save it as UTF-8 and try again."
        )

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ImportFormatError("The CSV file has no header row.")

    headers = {_normalize_header(name) for name in reader.fieldnames if name}
    missing = EXPECTED_HEADERS - headers
    if missing:
        joined = ", ".join(sorted(missing))
        raise ImportFormatError(f"Missing required column(s): {joined}")

    rows: list[dict[str, str]] = []
    for raw in reader:
        row = _normalize_row(raw)
        if not any(row.values()):
            continue
        rows.append(row)
    if not rows:
        raise ImportFormatError("The CSV file has no question rows.")
    return rows


def _explanation_steps(row: dict[str, str]) -> list[dict]:
    steps: list[dict] = []
    for index in range(1, 6):
        content = row.get(f"explanation_step_{index}", "").strip()
        if content:
            steps.append({"order": len(steps) + 1, "content": content})
    return steps


def _is_true_false_token(value: str) -> bool:
    token = (value or "").strip().casefold()
    return token in {"true", "false", "t", "f", "yes", "no", "1", "0"}


def _canonical_true_false(value: str) -> str:
    token = (value or "").strip().casefold()
    if token in {"true", "t", "yes", "1"}:
        return "True"
    if token in {"false", "f", "no", "0"}:
        return "False"
    return value.strip()


def _prepare_answers(
    row: dict[str, str],
    question_type: str,
) -> tuple[str, str, list[dict]]:
    """Return (correct_label, expected_answer, choices) for a CSV row."""
    correct_label = (row.get("correct_label") or "A").strip().upper() or "A"
    expected_answer = row.get("expected_answer", "").strip()
    if question_type == Question.QuestionType.TRUE_FALSE:
        if not expected_answer and _is_true_false_token(correct_label):
            expected_answer = correct_label
            correct_label = "A"
        expected_answer = _canonical_true_false(expected_answer)
    elif question_type == Question.QuestionType.ENUMERATION and expected_answer:
        expected_answer = expected_answer.replace("|", "\n").replace(";", "\n")

    choices_data = (
        _mcq_choices(row, correct_label)
        if question_type == Question.QuestionType.MCQ
        else []
    )
    return correct_label, expected_answer, choices_data


def _mcq_choices(row: dict[str, str], correct_label: str) -> list[dict]:
    choices: list[dict] = []
    for label in ("A", "B", "C", "D"):
        text = row.get(f"choice_{label.lower()}", "").strip()
        if text:
            choices.append(
                {
                    "label": label,
                    "text": text,
                    "is_correct": label == correct_label,
                }
            )
    return choices


def import_questions_from_csv(
    uploaded_file,
    *,
    subject: Subject,
    professor,
) -> ImportSummary:
    """Import questions from a CSV upload scoped to one course subject."""
    rows = _read_csv_rows(uploaded_file)
    summary = ImportSummary()
    seen_stems: set[str] = set()

    for offset, row in enumerate(rows, start=2):
        stem = row.get("stem", "").strip()
        stem_preview = stem[:60] if stem else f"Row {offset}"

        subject_code = row.get("subject_code", "")
        if not subject_code:
            summary.skipped_invalid += 1
            summary.row_errors.append(
                ImportRowError(offset, stem_preview, "subject_code is required.")
            )
            continue
        if not _codes_match(subject_code, subject.code):
            summary.skipped_invalid += 1
            summary.row_errors.append(
                ImportRowError(
                    offset,
                    stem_preview,
                    f"subject_code must be {subject.code} for this course.",
                )
            )
            continue

        topic_name = row.get("topic_name", "").strip()
        if not topic_name:
            summary.skipped_invalid += 1
            summary.row_errors.append(
                ImportRowError(offset, stem_preview, "topic_name is required.")
            )
            continue
        topic = Topic.objects.filter(subject=subject, name__iexact=topic_name).first()
        if topic is None:
            summary.skipped_invalid += 1
            summary.row_errors.append(
                ImportRowError(
                    offset,
                    stem_preview,
                    f'Topic "{topic_name}" was not found under {subject.code}.',
                )
            )
            continue

        question_type = _normalize_question_type(row.get("question_type", ""))
        if question_type not in VALID_TYPES:
            summary.skipped_invalid += 1
            summary.row_errors.append(
                ImportRowError(
                    offset,
                    stem_preview,
                    "question_type must be mcq, true_false, identification, or enumeration.",
                )
            )
            continue

        difficulty = _normalize_difficulty(row.get("difficulty", ""))
        if difficulty not in VALID_DIFFICULTIES:
            summary.skipped_invalid += 1
            summary.row_errors.append(
                ImportRowError(
                    offset,
                    stem_preview,
                    "difficulty must be easy, medium, or hard.",
                )
            )
            continue

        if not stem:
            summary.skipped_invalid += 1
            summary.row_errors.append(
                ImportRowError(offset, stem_preview, "stem is required.")
            )
            continue

        correct_label, expected_answer, choices_data = _prepare_answers(
            row,
            question_type,
        )

        stem_key = normalize_stem(stem)
        if stem_key in seen_stems:
            summary.skipped_duplicates += 1
            summary.row_errors.append(
                ImportRowError(
                    offset,
                    stem_preview,
                    "Duplicate question stem appears more than once in this file.",
                )
            )
            continue
        duplicate = find_duplicate_question(topic.pk, stem)
        if duplicate:
            summary.skipped_duplicates += 1
            summary.row_errors.append(
                ImportRowError(
                    offset,
                    stem_preview,
                    "Duplicate question stem already exists in the question bank.",
                )
            )
            continue

        validation = validate_question_for_submit(
            stem,
            choices_data,
            topic,
            difficulty,
            correct_label,
            ai_enabled=False,
            question_type=question_type,
            expected_answer=expected_answer,
        )
        if not validation.get("is_valid"):
            summary.skipped_invalid += 1
            summary.row_errors.append(
                ImportRowError(
                    offset,
                    stem_preview,
                    validation.get("feedback") or "Invalid question row.",
                )
            )
            continue

        seen_stems.add(stem_key)

        status = (row.get("status") or Question.Status.DRAFT).strip().casefold()
        if status not in VALID_STATUSES:
            status = Question.Status.DRAFT

        subject = getattr(topic, "subject", None)
        if subject is not None:
            from apps.questions.services import assert_subject_bank_has_capacity

            try:
                assert_subject_bank_has_capacity(subject, additional=1)
            except ValueError as exc:
                summary.skipped_invalid += 1
                summary.row_errors.append(
                    ImportRowError(offset, stem_preview, str(exc))
                )
                break

        question_payload = {
            "topic": topic,
            "difficulty": difficulty,
            "question_type": question_type,
            "stem": stem,
            "concept_tag": row.get("concept_tag", "").strip(),
            "expected_answer": (
                expected_answer if question_type != Question.QuestionType.MCQ else ""
            ),
            "is_active": _parse_bool(row.get("is_active", ""), default=False),
            "status": status,
            "proposed_by": professor,
            "explanation_status": "draft",
        }
        create_question(question_payload, choices_data, _explanation_steps(row))
        summary.created += 1

    return summary
