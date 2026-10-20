"""Tutor conversation persistence and chat orchestration."""

from __future__ import annotations

import json
import re
from typing import Any

from apps.ai.factory import get_tutor_engine
from apps.reviews.models import Answer, Question, ReviewSession, TutorConversation, TutorMessage
from apps.users.models import User


def get_or_create_conversation(student: User, question: Question) -> TutorConversation:
    conversation, _ = TutorConversation.objects.get_or_create(
        student=student,
        question=question,
    )
    return conversation


def clear_tutor_conversation_on_reanswer(
    student: User,
    question: Question,
    *,
    exclude_answer_pk: int | None = None,
) -> bool:
    """Remove prior tutor chat when a student answers the same question again."""
    prior_answers = Answer.objects.filter(
        session__student=student,
        question=question,
    )
    if exclude_answer_pk is not None:
        prior_answers = prior_answers.exclude(pk=exclude_answer_pk)
    if not prior_answers.exists():
        return False

    deleted, _ = TutorConversation.objects.filter(
        student=student,
        question=question,
    ).delete()
    return bool(deleted)


def _tutor_message_image_url(msg: TutorMessage) -> str:
    if not msg.image:
        return ""
    try:
        return msg.image.url
    except ValueError:
        return ""


def conversation_messages_payload(
    conversation: TutorConversation, *, subject_code: str = "", history_note: str = ""
) -> list[dict]:
    payload = []
    last_concept_entry: dict | None = None
    for msg in conversation.messages.order_by("created"):
        entry = {
            "id": msg.pk,
            "role": msg.role,
            "content": msg.content,
            "image_url": _tutor_message_image_url(msg),
            "image_name": (
                (msg.image.name.rsplit("/", 1)[-1] if msg.image else "") or ""
            ),
            "created_at": msg.created.isoformat(),
        }
        if msg.role == TutorMessage.Role.ASSISTANT:
            structured = parse_tutor_structured_reply(msg.content)
            if structured and subject_code:
                structured["subject_code"] = subject_code
            entry["structured"] = structured
            if structured and structured.get("type") == "concept_check":
                last_concept_entry = entry
        payload.append(entry)
    if history_note and last_concept_entry and last_concept_entry.get("structured"):
        # Show the current repeat-miss status once, on the latest concept check.
        last_concept_entry["structured"]["history_note"] = history_note
    return payload


def conversation_history(conversation: TutorConversation, limit: int = 40) -> list[dict[str, str]]:
    return [
        {"role": msg.role, "text": msg.content}
        for msg in conversation.messages.order_by("created")[:limit]
    ]


def _answer_user_response(answer: Answer) -> str:
    return format_answer_user_text(answer)


def format_answer_user_text(answer: Answer) -> str:
    if answer.timed_out:
        return "Timed out"
    if answer.selected_choice_id:
        choice = answer.selected_choice
        return f"{choice.label}: {choice.text}"
    if answer.numeric_response:
        return str(answer.numeric_response).strip()
    return "No answer"


def _answer_correct_response(answer: Answer) -> str:
    return format_question_correct_text(answer.question)


def format_question_correct_text(question: Question) -> str:
    if question.question_type == question.QuestionType.MCQ:
        correct = question.choices.filter(is_correct=True).first()
        if correct:
            return f"{correct.label}: {correct.text}"
    if question.expected_answer:
        return str(question.expected_answer).strip()
    if question.correct_answer is not None:
        return str(question.correct_answer)
    return "Unknown"


def _question_context(answer: Answer | None) -> dict:
    if not answer:
        return {}
    from apps.questions.services import (
        adaptive_explanation_has_content,
        clean_adaptive_explanation,
        question_explanation_step_texts,
    )

    question = answer.question
    steps = question_explanation_step_texts(question)
    adaptive = clean_adaptive_explanation(
        getattr(question, "adaptive_explanation", None)
    )
    subject = (
        question.topic.subject if question.topic and question.topic.subject_id else None
    )
    ctx = {
        "stem": question.stem,
        "subject_code": getattr(subject, "code", "") or "",
        "subject_name": getattr(subject, "name", "") or "",
        "user_answer": _answer_user_response(answer),
        "correct_answer": _answer_correct_response(answer),
        "is_correct": answer.is_correct,
        "timed_out": answer.timed_out,
        "difficulty": question.difficulty,
    }
    if question.question_type == question.QuestionType.MCQ:
        choices = [
            {"id": choice.label, "text": choice.text}
            for choice in question.choices.all().order_by("label")
        ]
        if choices:
            ctx["choices"] = choices
            correct = next(
                (c for c in question.choices.all() if c.is_correct), None
            )
            if correct:
                ctx["correct_pick"] = correct.label
            if answer.selected_choice_id and answer.selected_choice:
                ctx["student_pick"] = answer.selected_choice.label
    if steps:
        ctx["explanation_steps"] = steps
    if adaptive_explanation_has_content(adaptive):
        ctx["adaptive_explanation"] = adaptive
    return ctx


def _concept_history_note(student: User, question: Question) -> str:
    """Return a server-owned note after repeated misses on a concept."""
    from apps.analytics.concept_review_services import concept_key_for_question
    from apps.analytics.models import ConceptReview

    key, fallback_name = concept_key_for_question(question)
    review = (
        ConceptReview.objects.filter(student=student, concept_key=key)
        .only("concept_name", "miss_count", "status")
        .first()
    )
    if not review or review.miss_count < 2:
        return ""
    if review.status == ConceptReview.Status.RESOLVED:
        return ""
    concept_name = (review.concept_name or fallback_name).strip()
    if review.miss_count == 2:
        return f"Second miss on {concept_name}. Saved to Concepts to Review."
    return (
        f"Missed {review.miss_count} times on {concept_name}. "
        "Saved to Concepts to Review."
    )


def _exam_context(session: ReviewSession, answer: Answer | None = None) -> dict:
    subject = session.topic.subject if session.topic.subject_id else None
    ctx = {
        "subject": subject.name if subject else "",
        "subject_code": (getattr(subject, "code", "") or "") if subject else "",
        "topic": session.topic.name,
        "exam_name": f"{session.topic.name} ({session.get_difficulty_display()})",
    }
    if answer:
        ctx.update(_question_context(answer))
    return ctx


def session_answer_items(session: ReviewSession) -> list[dict]:
    """Build tutor item payloads without blocking on LLM calls."""
    from apps.analytics.confidence import answer_is_unanswered, confidence_tier_key
    from apps.analytics.services import get_answer_feedback_quick

    items = []
    answers = (
        session.answers.select_related(
            "question",
            "selected_choice",
            "question__topic",
            "mistake_record",
        )
        .prefetch_related("question__choices", "question__explanation_steps")
        .order_by("answered_at")
    )
    for answer in answers:
        step_rows = list(
            answer.question.explanation_steps.order_by("order").values(
                "content", "professor_note", "order"
            )
        )
        steps = []
        faculty_notes = []
        for row in step_rows:
            content = (row.get("content") or "").strip()
            note = (row.get("professor_note") or "").strip()
            if content:
                steps.append(content)
            if note:
                faculty_notes.append(note)
        mistake = getattr(answer, "mistake_record", None)
        if mistake and (mistake.faculty_note or "").strip():
            faculty_notes.append(mistake.faculty_note.strip())
        concern_messages = []
        correct_answer = _answer_correct_response(answer)
        conv = TutorConversation.objects.filter(
            student=session.student,
            question=answer.question,
        ).first()
        feedback, needs_ai = get_answer_feedback_quick(answer)
        from apps.ai.normalize import parse_any_adaptive_feedback
        from apps.analytics.services import question_feedback_is_faculty_validated

        structured = parse_any_adaptive_feedback(feedback)
        unanswered = answer_is_unanswered(answer)
        faculty_validated = question_feedback_is_faculty_validated(answer.question)
        items.append(
            {
                "answer_id": answer.pk,
                "question_id": answer.question_id,
                "session_id": session.pk,
                "mistake_id": mistake.pk if mistake else None,
                "stem": answer.question.stem,
                "is_correct": bool(answer.is_correct) and not unanswered,
                "timed_out": answer.timed_out,
                "unanswered": unanswered,
                "no_selection": unanswered,
                "confidence_tier": confidence_tier_key(answer.confidence),
                "feedback": feedback,
                "structured_feedback": structured,
                "needs_ai": needs_ai,
                "correction_steps": steps,
                "faculty_notes": faculty_notes,
                "concern_messages": concern_messages,
                "user_answer": _answer_user_response(answer),
                "correct_answer": correct_answer,
                "final_answer": correct_answer,
                "topic": answer.question.topic.name,
                "difficulty": answer.question.get_difficulty_display(),
                "message_count": conv.messages.count() if conv else 0,
                "feedback_validated_by_faculty": faculty_validated,
                "steps_validated_by_faculty": (
                    answer.question.explanation_status == "faculty_approved"
                ),
            }
        )
    return items


def tutor_history_payload(session: ReviewSession, *, answer_id: int | None = None) -> dict:
    items = session_answer_items(session)
    active_answer_id = answer_id
    if not active_answer_id and items:
        wrong = [item for item in items if not item["is_correct"]]
        pool = wrong if wrong else items
        active_answer_id = pool[0]["answer_id"]

    messages = []
    if active_answer_id:
        answer = (
            Answer.objects.filter(pk=active_answer_id, session=session)
            .select_related(
                "question",
                "selected_choice",
                "question__topic",
                "question__topic__subject",
            )
            .first()
        )
        if answer:
            conversation = TutorConversation.objects.filter(
                student=session.student,
                question=answer.question,
            ).first()
            if conversation:
                subject = (
                    answer.question.topic.subject
                    if answer.question.topic_id
                    and answer.question.topic.subject_id
                    else None
                )
                messages = conversation_messages_payload(
                    conversation,
                    subject_code=(getattr(subject, "code", "") or ""),
                    history_note=_concept_history_note(
                        session.student, answer.question
                    ),
                )

    return {
        "messages": messages,
        "active_answer_id": active_answer_id,
        "items": items,
    }


def coerce_plain_solution(text: str) -> dict | None:
    """Turn a plain numbered math solution into structured tutor JSON."""
    import re

    raw = (text or "").strip()
    if not raw:
        return None

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) < 2:
        return None

    step_pattern = re.compile(
        r"^(?:step\s*)?(\d+)[.)]\s*(.+)$",
        re.IGNORECASE,
    )
    steps: list[dict] = []
    answer = ""
    current: dict | None = None

    def _action_title(body: str, fallback: str) -> str:
        cleaned = re.sub(r"^step\s*\d+\s*[:.\-]\s*", "", body or "", flags=re.I).strip()
        if not cleaned:
            return fallback
        if _looks_like_math_line(cleaned):
            return fallback
        words = cleaned.split()
        if len(words) > 8:
            cleaned = " ".join(words[:8])
        return cleaned[:48].rstrip(".,;:")

    def flush() -> None:
        nonlocal current
        if current and (current.get("operation") or current.get("equations")):
            steps.append(current)
        current = None

    for line in lines:
        answer_match = re.match(
            r"^(?:final\s+)?answer\s*[:=-]\s*(.+)$",
            line,
            re.IGNORECASE,
        )
        if answer_match:
            flush()
            answer = answer_match.group(1).strip()
            continue

        match = step_pattern.match(line)
        if match:
            flush()
            body = match.group(2).strip()
            current = {
                "title": _action_title(body, "Continue"),
                "operation": "",
                "equations": [],
                "highlight": "",
                "note": "",
                "why": "",
            }
            if _looks_like_math_line(body):
                current["equations"].append(body)
                current["title"] = "Continue"
            else:
                current["title"] = _action_title(body, "Continue")
            continue

        if current is None:
            return None
        if _looks_like_math_line(line):
            current.setdefault("equations", []).append(line)
        elif not current.get("operation"):
            current["operation"] = line
        else:
            current["operation"] = f"{current['operation']} {line}".strip()

    flush()

    if len(steps) < 2:
        return None

    math_lines = sum(
        1
        for step in steps
        for eq in step.get("equations", [])
        if _looks_like_math_line(eq)
    )
    if math_lines == 0 and not _looks_like_math_line(answer):
        return None

    return {"type": "solution", "steps": steps, "answer": answer}


def _looks_like_math_line(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if t.startswith("$") or "$$" in t:
        return True
    if re.search(r"\\frac|\\sqrt|\\sum|\\int|\\xrightarrow|\\text\{", t):
        return True
    if re.search(r"[=+\-×÷^√≤≥≠≈]", t) and re.search(r"[0-9a-zA-Z]", t):
        return True
    return False


MAX_TABLE_COLUMNS = 6
MAX_TABLE_ROWS = 20


def _normalize_table_block(block: dict) -> dict | None:
    """Validate a text table block; None when malformed."""
    headers_raw = block.get("headers")
    rows_raw = block.get("rows")
    if not isinstance(headers_raw, list) or not isinstance(rows_raw, list):
        return None
    headers = [
        str(value).strip() if value is not None else "" for value in headers_raw
    ]
    if not 2 <= len(headers) <= MAX_TABLE_COLUMNS:
        return None
    if any(not header for header in headers):
        return None
    rows: list[list[str]] = []
    for row in rows_raw[:MAX_TABLE_ROWS]:
        if not isinstance(row, list) or len(row) != len(headers):
            continue
        cells = [
            str(cell).strip() if cell is not None else "" for cell in row
        ]
        if not any(cells):
            continue
        rows.append(cells)
    if not rows:
        return None
    return {"kind": "table", "headers": headers, "rows": rows}


def _normalize_text_blocks(blocks: Any) -> list[dict]:
    """Return cleaned text blocks; empty list when the shape is invalid."""
    if not isinstance(blocks, list):
        return []
    cleaned: list[dict] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        kind = block.get("kind")
        if kind == "paragraph":
            text = str(block.get("text") or "").strip()
            if text:
                cleaned.append({"kind": "paragraph", "text": text})
        elif kind == "list":
            items = block.get("items")
            items = [
                str(item).strip()
                for item in items
                if str(item or "").strip()
            ] if isinstance(items, list) else []
            if items:
                cleaned.append({"kind": "list", "items": items})
        elif kind == "table":
            table = _normalize_table_block(block)
            if table:
                cleaned.append(table)
        elif kind == "math":
            latex = str(block.get("latex") or "").strip()
            if latex:
                cleaned.append({"kind": "math", "latex": latex})
    return cleaned


def _blocks_plain_text(blocks: list[dict]) -> str:
    """Plain-text fallback for a normalized blocks list (math is skipped)."""
    parts: list[str] = []
    for block in blocks:
        kind = block.get("kind")
        if kind == "math":
            continue
        if kind == "list":
            parts.extend(str(item) for item in (block.get("items") or []) if item)
        elif kind == "table":
            headers = block.get("headers") or []
            if headers:
                parts.append(" | ".join(str(item) for item in headers))
            for row in block.get("rows") or []:
                parts.append(" | ".join(str(cell) for cell in row))
        else:
            parts.append(str(block.get("text") or "").strip())
    parts = [p for p in parts if p]
    return "\n".join(parts)


def _parse_concept_check(data: dict) -> dict | None:
    """Validate and normalize a concept_check reply; None when malformed."""
    options_raw = data.get("options")
    if not isinstance(options_raw, list) or not options_raw:
        return None
    options: list[dict] = []
    for option in options_raw:
        if not isinstance(option, dict):
            return None
        option_id = str(option.get("id") or "").strip()
        if not option_id:
            return None
        normalized = {
            "id": option_id,
            "fits": bool(option.get("fits")),
            "reason": str(option.get("reason") or "").strip(),
        }
        option_text = str(option.get("text") or "").strip()
        if option_text:
            normalized["text"] = option_text
        option_tag = str(option.get("tag") or "").strip()
        if option_tag:
            normalized["tag"] = option_tag
        options.append(normalized)
    correct = str(data.get("correct") or "").strip()
    if not correct:
        return None
    symbolic_raw = data.get("symbolic")
    if isinstance(symbolic_raw, dict) and str(symbolic_raw.get("latex") or "").strip():
        symbolic = {
            "latex": str(symbolic_raw.get("latex")).strip(),
            "explain": str(symbolic_raw.get("explain") or "").strip(),
        }
    else:
        symbolic = None
    follow_ups_raw = data.get("follow_ups")
    follow_ups = (
        [str(value).strip() for value in follow_ups_raw if str(value or "").strip()]
        if isinstance(follow_ups_raw, list)
        else []
    )
    return {
        "type": "concept_check",
        "student_pick": str(data.get("student_pick") or "").strip() or None,
        "correct": correct,
        "mistake": str(data.get("mistake") or "").strip() or None,
        "rule": str(data.get("rule") or "").strip(),
        "options": options,
        "symbolic": symbolic,
        "quick_check": str(data.get("quick_check") or "").strip() or None,
        "remember": str(data.get("remember") or "").strip() or None,
        "follow_ups": follow_ups,
    }


def _validate_solution_steps(steps: list) -> bool:
    """Solution steps must be dicts; any latex field must be a list of strings."""
    for step in steps:
        if not isinstance(step, dict):
            return False
        latex = step.get("latex")
        if latex is not None:
            if not isinstance(latex, list):
                return False
            if not all(isinstance(line, str) for line in latex):
                return False
    return True


def parse_tutor_structured_reply(reply: str) -> dict | None:
    """Extract structured tutor JSON from a model reply, if present."""
    import re

    text = (reply or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            coerced = coerce_plain_solution(text)
            return coerced
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return coerce_plain_solution(text)
    if not isinstance(data, dict):
        return coerce_plain_solution(text)

    response_type = data.get("type")

    if response_type == "concept_check":
        return _parse_concept_check(data) or coerce_plain_solution(text)

    steps = data.get("steps")
    if steps is not None and not isinstance(steps, list):
        return None

    if response_type == "solution" or (steps and len(steps) > 0):
        if not _validate_solution_steps(steps or []):
            return coerce_plain_solution(text)
        steps = steps or []
        answer = data.get("answer") or ""
        # Legacy redirect replies used a single prose step with no math and
        # no answer; treat those as plain text so history keeps rendering.
        if (
            len(steps) == 1
            and not steps[0].get("equations")
            and not steps[0].get("latex")
            and not str(answer or "").strip()
        ):
            content = _blocks_plain_text(
                [
                    {
                        "kind": "paragraph",
                        "text": "\n".join(
                            part
                            for part in (
                                str(steps[0].get("title") or ""),
                                str(steps[0].get("operation") or ""),
                                str(steps[0].get("note") or ""),
                                str(steps[0].get("why") or ""),
                            )
                            if part.strip()
                        ),
                    }
                ]
            )
            if content:
                return {"type": "text", "content": content}
        result: dict = {
            "type": "solution",
            "steps": steps,
            "answer": answer,
            "chart": data.get("chart"),
        }
        check = data.get("check")
        if isinstance(check, str) and check.strip():
            result["check"] = check.strip()
        follow_ups_raw = data.get("follow_ups")
        if isinstance(follow_ups_raw, list):
            follow_ups = [
                str(value).strip()
                for value in follow_ups_raw
                if str(value or "").strip()
            ]
            if follow_ups:
                result["follow_ups"] = follow_ups
        return result

    blocks = _normalize_text_blocks(data.get("blocks"))
    content = (data.get("content") or "").strip()
    follow_ups_raw = data.get("follow_ups")
    follow_ups = (
        [str(value).strip() for value in follow_ups_raw if str(value or "").strip()]
        if isinstance(follow_ups_raw, list)
        else []
    )
    remember = str(data.get("remember") or "").strip()
    if response_type == "text" or blocks:
        if blocks:
            result = {
                "type": "text",
                "content": content or _blocks_plain_text(blocks),
                "blocks": blocks,
            }
            if follow_ups:
                result["follow_ups"] = follow_ups
            if remember:
                result["remember"] = remember
            return result
        if content:
            result = {"type": "text", "content": content}
            if follow_ups:
                result["follow_ups"] = follow_ups
            if remember:
                result["remember"] = remember
            return result
        if response_type == "text":
            return None

    content = (data.get("content") or data.get("answer") or "").strip()
    if content:
        return {"type": "text", "content": content}
    return coerce_plain_solution(text)


def process_tutor_chat(
    session: ReviewSession,
    user_message: str,
    *,
    answer_id: int | None = None,
    image=None,
) -> dict:
    user_message = (user_message or "").strip()
    if not user_message and not image:
        return {"error": "Add a message or photo."}

    answer = None
    if answer_id:
        answer = (
            Answer.objects.filter(pk=answer_id, session=session)
            .select_related(
                "question",
                "selected_choice",
                "question__topic",
                "question__topic__subject",
            )
            .first()
        )
    if not answer:
        return {"error": "Select a question to discuss."}

    conversation = get_or_create_conversation(session.student, answer.question)

    prompt_message = user_message
    if image and not prompt_message:
        prompt_message = "I attached a photo of my work. Please help with this question."
    elif image:
        prompt_message = f"{user_message}\n\n[Student attached an image of their work.]"

    user_msg = TutorMessage.objects.create(
        conversation=conversation,
        role=TutorMessage.Role.USER,
        content=user_message,
        answer=answer,
        image=image,
    )

    history = conversation_history(conversation)
    exam_context = _exam_context(session, answer)
    question_context = _question_context(answer)

    reply = get_tutor_engine().chat(
        topic=session.topic.name,
        message=prompt_message,
        history=history[:-1],
        exam_context=exam_context,
        question_context=question_context,
    )

    structured = parse_tutor_structured_reply(reply)
    subject_code = (question_context.get("subject_code") or "").strip()
    if structured and subject_code:
        structured["subject_code"] = subject_code
    if structured and structured.get("type") == "concept_check":
        history_note = _concept_history_note(session.student, answer.question)
        if history_note:
            structured["history_note"] = history_note
    assistant_msg = TutorMessage.objects.create(
        conversation=conversation,
        role=TutorMessage.Role.ASSISTANT,
        content=reply,
        answer=answer,
    )

    return {
        "reply": reply,
        "structured": structured,
        "message_id": assistant_msg.pk,
        "user_message": {
            "id": user_msg.pk,
            "role": user_msg.role,
            "content": user_msg.content or "",
            "image_url": _tutor_message_image_url(user_msg),
            "image_name": (
                (user_msg.image.name.rsplit("/", 1)[-1] if user_msg.image else "") or ""
            ),
        },
        "active_answer_id": answer.pk,
        "question_id": answer.question_id,
    }
