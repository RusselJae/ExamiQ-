"""Tutor conversation persistence and chat orchestration."""

from __future__ import annotations

from apps.ai.factory import get_tutor_engine
from apps.reviews.models import Answer, Question, ReviewSession, TutorConversation, TutorMessage
from apps.users.models import User


def get_or_create_conversation(student: User, question: Question) -> TutorConversation:
    conversation, _ = TutorConversation.objects.get_or_create(
        student=student,
        question=question,
    )
    return conversation


def conversation_messages_payload(conversation: TutorConversation) -> list[dict]:
    return [
        {
            "id": msg.pk,
            "role": msg.role,
            "content": msg.content,
            "created_at": msg.created.isoformat(),
        }
        for msg in conversation.messages.order_by("created")
    ]


def conversation_history(conversation: TutorConversation, limit: int = 40) -> list[dict[str, str]]:
    return [
        {"role": msg.role, "text": msg.content}
        for msg in conversation.messages.order_by("created")[:limit]
    ]


def _answer_user_response(answer: Answer) -> str:
    if answer.timed_out:
        return "Timed out"
    if answer.selected_choice_id:
        choice = answer.selected_choice
        return f"{choice.label}: {choice.text}"
    if answer.numeric_response:
        return str(answer.numeric_response)
    return "No answer"


def _answer_correct_response(answer: Answer) -> str:
    question = answer.question
    if question.question_type == question.QuestionType.MCQ:
        correct = question.choices.filter(is_correct=True).first()
        if correct:
            return f"{correct.label}: {correct.text}"
    elif question.correct_answer is not None:
        return str(question.correct_answer)
    return "Unknown"


def _question_context(answer: Answer | None) -> dict:
    if not answer:
        return {}
    return {
        "stem": answer.question.stem,
        "user_answer": _answer_user_response(answer),
        "correct_answer": _answer_correct_response(answer),
        "is_correct": answer.is_correct,
        "timed_out": answer.timed_out,
        "difficulty": answer.question.difficulty,
    }


def _exam_context(session: ReviewSession, answer: Answer | None = None) -> dict:
    ctx = {
        "topic": session.topic.name,
        "subject": session.topic.subject.name if session.topic.subject_id else "",
        "exam_name": f"{session.topic.name} ({session.get_difficulty_display()})",
    }
    if answer:
        ctx.update(_question_context(answer))
    return ctx


def session_answer_items(session: ReviewSession) -> list[dict]:
    from apps.analytics.confidence import confidence_tier_key
    from apps.analytics.services import generate_answer_feedback

    items = []
    answers = (
        session.answers.select_related("question", "selected_choice", "question__topic")
        .prefetch_related("question__choices", "question__explanation_steps")
        .order_by("answered_at")
    )
    for answer in answers:
        steps = list(
            answer.question.explanation_steps.order_by("order").values_list("content", flat=True)
        )
        conv = TutorConversation.objects.filter(
            student=session.student,
            question=answer.question,
        ).first()
        items.append(
            {
                "answer_id": answer.pk,
                "question_id": answer.question_id,
                "stem": answer.question.stem,
                "is_correct": answer.is_correct,
                "timed_out": answer.timed_out,
                "confidence_tier": confidence_tier_key(answer.confidence),
                "feedback": generate_answer_feedback(answer),
                "correction_steps": steps,
                "topic": answer.question.topic.name,
                "difficulty": answer.question.get_difficulty_display(),
                "message_count": conv.messages.count() if conv else 0,
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
        answer = Answer.objects.filter(pk=active_answer_id, session=session).select_related("question").first()
        if answer:
            conversation = TutorConversation.objects.filter(
                student=session.student,
                question=answer.question,
            ).first()
            if conversation:
                messages = conversation_messages_payload(conversation)

    return {
        "messages": messages,
        "active_answer_id": active_answer_id,
        "items": items,
    }


def process_tutor_chat(
    session: ReviewSession,
    user_message: str,
    *,
    answer_id: int | None = None,
) -> dict:
    user_message = (user_message or "").strip()
    if not user_message:
        return {"error": "Message cannot be empty."}

    answer = None
    if answer_id:
        answer = Answer.objects.filter(pk=answer_id, session=session).select_related("question").first()
    if not answer:
        return {"error": "Select a question to discuss."}

    conversation = get_or_create_conversation(session.student, answer.question)

    TutorMessage.objects.create(
        conversation=conversation,
        role=TutorMessage.Role.USER,
        content=user_message,
        answer=answer,
    )

    history = conversation_history(conversation)
    exam_context = _exam_context(session, answer)
    question_context = _question_context(answer)

    reply = get_tutor_engine().chat(
        topic=session.topic.name,
        message=user_message,
        history=history[:-1],
        exam_context=exam_context,
        question_context=question_context,
    )

    assistant_msg = TutorMessage.objects.create(
        conversation=conversation,
        role=TutorMessage.Role.ASSISTANT,
        content=reply,
        answer=answer,
    )

    return {
        "reply": reply,
        "message_id": assistant_msg.pk,
        "active_answer_id": answer.pk,
        "question_id": answer.question_id,
    }
