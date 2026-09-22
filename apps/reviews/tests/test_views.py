import pytest
from django.urls import reverse

from apps.questions.models import Question, YearLevel
from apps.reviews.models import ReviewSession
from apps.reviews.services import start_review_session, submit_answer


@pytest.mark.django_db
class TestQuestionPartialView:
    def test_htmx_returns_exam_results_when_no_questions(self, client, student, topic):
        session = ReviewSession.objects.create(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            status=ReviewSession.Status.ACTIVE,
            planned_question_count=0,
            mode=ReviewSession.Mode.TIMED_EXAM,
        )
        client.force_login(student)
        url = reverse("reviews:question_partial", kwargs={"pk": session.pk})
        response = client.get(url, HTTP_HX_REQUEST="true")

        assert response.status_code == 200
        content = response.content.decode()
        assert "Exam submitted!" in content
        assert "exam-results-card" in content
        session.refresh_from_db()
        assert session.status == ReviewSession.Status.COMPLETED

    def test_exam_results_shows_mapped_average_confidence_label(
        self, client, student, topic, mcq_question
    ):
        question, _ = mcq_question
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
        )
        wrong = question.choices.filter(is_correct=False).first()
        submit_answer(
            session=session,
            question=question,
            confidence=5,
            selected_choice=wrong,
            time_spent_seconds=5,
        )

        client.force_login(student)
        url = reverse("reviews:question_partial", kwargs={"pk": session.pk})
        response = client.get(url, HTTP_HX_REQUEST="true")
        content = response.content.decode()
        assert response.status_code == 200
        assert "Sure" in content
        assert "Average confidence" in content
        assert "Incorrect answers" not in content

    def test_non_htmx_redirects_to_session(self, client, student, topic, mcq_question):
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
        )
        client.force_login(student)
        url = reverse("reviews:question_partial", kwargs={"pk": session.pk})
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse("reviews:session", kwargs={"pk": session.pk})

    def test_renders_question_when_available(self, client, student, topic, mcq_question):
        question, _ = mcq_question
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.PRACTICE_REVIEW,
        )
        client.force_login(student)
        url = reverse("reviews:question_partial", kwargs={"pk": session.pk})
        response = client.get(url, HTTP_HX_REQUEST="true")

        assert response.status_code == 200
        content = response.content.decode()
        assert question.stem in content
        assert "confidence-btn" in content

    def test_question_partial_shows_per_question_subject(
        self, client, student, topic, mcq_question, program, year_level
    ):
        from apps.questions.models import Subject, Topic

        other_subject = Subject.objects.create(
            program=program,
            code="MMW-2",
            name="Mathematics in the Modern World",
            year_level=year_level,
            semester=1,
        )
        other_topic = Topic.objects.create(subject=other_subject, name="20th Century")
        other_q = Question.objects.create(
            topic=other_topic,
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.ENUMERATION,
            stem="List two branches.",
            status=Question.Status.APPROVED,
            expected_answer="Set theory",
        )

        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
            question_queue=[other_q.pk],
        )
        client.force_login(student)
        url = reverse("reviews:question_partial", kwargs={"pk": session.pk})
        response = client.get(url, HTTP_HX_REQUEST="true")
        content = response.content.decode()

        assert response.status_code == 200
        assert "Mathematics in the Modern World" in content
        assert "Enumeration" in content

    def test_timed_exam_shows_confidence_gate(self, client, student, topic, mcq_question):
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
        )
        client.force_login(student)
        url = reverse("reviews:question_partial", kwargs={"pk": session.pk})
        response = client.get(url, HTTP_HX_REQUEST="true")
        content = response.content.decode()
        assert response.status_code == 200
        assert "exam-confidence-gate" in content
        assert "Guessing" in content
        assert "Not sure" in content
        assert "Sure" in content
        assert "question-timer-display" in content


@pytest.mark.django_db
class TestReviewSessionFocusUI:
    def test_session_page_loads_without_session_modals(self, client, student, topic, mcq_question):
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
        )
        client.force_login(student)
        response = client.get(reverse("reviews:session", kwargs={"pk": session.pk}))
        content = response.content.decode()
        assert response.status_code == 200
        assert "focus-header" in content
        assert "session-modal-icebreaker" not in content
        assert 'data-intro-pending="false"' in content
        assert "Loading first question" in content


@pytest.mark.django_db
class TestReviewSetupPage:
    def test_setup_includes_course_difficulty_and_modals(
        self, client, student, mcq_question, bsed_program, subject
    ):
        from conftest import make_bsed_student

        make_bsed_student(student, subject=subject, bsed_program=bsed_program)

        client.force_login(student)
        response = client.get(reverse("reviews:setup"))
        content = response.content.decode()
        assert response.status_code == 200
        assert "id_setup_subjects" not in content
        assert "Course subjects for your year" in content
        assert "id_setup_difficulty" in content
        assert "id_setup_question_type" in content
        assert "How this works" in content
        assert "up to 100 total" in content
        assert "Numeric Answer" not in content
        assert "exam-setup-summary" in content
        assert "pre-exam-step-goal" in content
        assert "pre-exam-step-warmup" not in content
        assert "review_window" not in content
        assert "Open review windows" not in content


@pytest.mark.django_db
class TestReviewSetupPrefill:
    def test_setup_shows_year_course_subjects(
        self, client, student, topic, mcq_question, bsed_program
    ):
        from conftest import make_bsed_student

        make_bsed_student(
            student, subject=topic.subject, bsed_program=bsed_program
        )

        client.force_login(student)
        response = client.get(reverse("reviews:setup"))
        assert response.status_code == 200
        content = response.content.decode()
        assert topic.subject.code in content
        assert "id_setup_subjects" not in content
        assert "Course subjects for your year" in content
        assert "exam-subject-card" in content
        assert "id_setup_difficulty" in content

    def test_setup_lists_only_student_year_subjects(
        self, client, student, year_level, bsed_program, mcq_question, subject
    ):
        from apps.questions.models import Subject, Topic
        from conftest import make_bsed_student

        make_bsed_student(student, subject=subject, bsed_program=bsed_program)

        other_year, _ = YearLevel.objects.get_or_create(
            order=99, defaults={"name": "Other Year"}
        )
        other_subject = Subject.objects.create(
            program=bsed_program,
            code="OTH-101",
            name="Other Subject",
            year_level=other_year,
            semester=1,
        )
        Topic.objects.create(subject=other_subject, name="Other Topic")
        client.force_login(student)
        response = client.get(reverse("reviews:setup"))
        assert response.status_code == 200
        content = response.content.decode()
        assert subject.code in content
        assert "Add subjects from other years" in content
        assert "OTH-101" in content
        year_subjects = response.context["year_subjects"]
        assert all(s.year_level_id == student.year_level_id for s in year_subjects)
        other_subjects = response.context["other_subjects"]
        assert any(s.code == "OTH-101" for s in other_subjects)

@pytest.mark.django_db
class TestSessionSummaryView:
    def test_summary_shows_answer_review_and_ai_tutor_modal(
        self, client, student, topic, mcq_question
    ):
        question, _ = mcq_question
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
        )
        wrong = question.choices.filter(is_correct=False).first()
        submit_answer(
            session=session,
            question=question,
            confidence=5,
            selected_choice=wrong,
            time_spent_seconds=5,
        )
        session.status = ReviewSession.Status.COMPLETED
        session.save(update_fields=["status"])

        client.force_login(student)
        response = client.get(reverse("reviews:summary", kwargs={"pk": session.pk}))
        content = response.content.decode()
        assert response.status_code == 200
        assert "answer-review" in content
        assert "Exam result" in content
        assert "Average confidence" in content
        assert "Sure" in content or "Not sure" in content or "Guessing" in content
        assert "Incorrect answers" not in content
        assert "Confidence gap" not in content
        assert "calibration-matrix" not in content
        assert "Topics to revisit" not in content
        assert "Answer review" in content
        assert "Result + pace" in content
        assert "answer-review-grid" in content
        assert "ai-tutor-modal" in content
        assert "ai-tutor-modal.js" in content
        assert "tutor-visual-response.js" in content
        assert "open-ai-tutor-btn" in content
        assert "ai-tutor-correct-banner" in content
        assert "openOnLoad: false" in content
        assert "studentName:" in content

        tutor_response = client.get(
            reverse("reviews:summary", kwargs={"pk": session.pk}) + "?open_tutor=1"
        )
        assert "openOnLoad: true" in tutor_response.content.decode()


@pytest.mark.django_db
class TestSubmitAnswerView:
    def test_timed_exam_stores_posted_sure_confidence(
        self, client, student, topic, mcq_question
    ):
        question, correct = mcq_question
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
        )
        client.force_login(student)
        url = reverse("reviews:submit_answer", kwargs={"pk": session.pk, "question_id": question.pk})
        response = client.post(
            url,
            {
                "selected_choice": correct.pk,
                "confidence": "5",
                "time_spent_seconds": "5",
                "timed_out": "false",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "data-exam-reveal" in content
        assert "answer-reveal-card" in content
        answer = session.answers.get()
        assert answer.confidence == 5

    def test_timed_submit_returns_reveal_partial(self, client, student, topic, mcq_question):
        question, correct = mcq_question
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
        )
        session.planned_question_count = 1
        session.save(update_fields=["planned_question_count"])
        client.force_login(student)
        url = reverse("reviews:submit_answer", kwargs={"pk": session.pk, "question_id": question.pk})
        response = client.post(
            url,
            {
                "selected_choice": correct.pk,
                "confidence": "3",
                "time_spent_seconds": "5",
                "timed_out": "false",
            },
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert "data-exam-reveal" in content
        assert "data-results-url" in content

    def test_timed_exam_stores_posted_not_sure_confidence(
        self, client, student, topic, mcq_question
    ):
        question, correct = mcq_question
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
        )
        client.force_login(student)
        url = reverse("reviews:submit_answer", kwargs={"pk": session.pk, "question_id": question.pk})
        response = client.post(
            url,
            {
                "selected_choice": correct.pk,
                "confidence": "3",
                "time_spent_seconds": "15",
                "timed_out": "false",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code in (200, 204)
        assert session.answers.get().confidence == 3

    def test_timed_exam_requires_confidence_on_timeout(
        self, client, student, topic, mcq_question
    ):
        question, correct = mcq_question
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
            seconds_per_question=30,
        )
        client.force_login(student)
        url = reverse("reviews:submit_answer", kwargs={"pk": session.pk, "question_id": question.pk})
        response = client.post(
            url,
            {
                "selected_choice": correct.pk,
                "confidence": "1",
                "time_spent_seconds": "30",
                "timed_out": "true",
            },
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code in (200, 204)
        assert session.answers.get().confidence == 1

    def test_timed_exam_rejects_submit_without_confidence(
        self, client, student, topic, mcq_question
    ):
        question, correct = mcq_question
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
            seconds_per_question=60,
        )
        client.force_login(student)
        url = reverse("reviews:submit_answer", kwargs={"pk": session.pk, "question_id": question.pk})
        response = client.post(
            url,
            {
                "selected_choice": correct.pk,
                "time_spent_seconds": "20",
                "timed_out": "false",
            },
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        assert session.answers.count() == 0
        assert "exam-form-error" in response.content.decode()


@pytest.mark.django_db
class TestTutorChat:
    def test_tutor_chat_persists_messages(self, client, student, topic, mcq_question):
        question, correct = mcq_question
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
        )
        answer = submit_answer(
            session=session,
            question=question,
            confidence=4,
            selected_choice=correct,
            time_spent_seconds=8,
        )
        session.status = ReviewSession.Status.COMPLETED
        session.save(update_fields=["status"])

        client.force_login(student)
        chat_url = reverse("reviews:tutor_chat", kwargs={"pk": session.pk})
        response = client.post(
            chat_url,
            data='{"message": "Why was my approach wrong?", "answer_id": %d}' % answer.pk,
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["reply"]

        from apps.reviews.models import TutorConversation, TutorMessage

        conversation = TutorConversation.objects.get(student=student, question=question)
        assert TutorMessage.objects.filter(conversation=conversation).count() == 2

    def test_tutor_chat_accepts_image(self, client, student, topic, mcq_question):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.reviews.models import TutorMessage

        question, correct = mcq_question
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
        )
        answer = submit_answer(
            session=session,
            question=question,
            confidence=4,
            selected_choice=correct,
            time_spent_seconds=8,
        )
        session.status = ReviewSession.Status.COMPLETED
        session.save(update_fields=["status"])

        client.force_login(student)
        chat_url = reverse("reviews:tutor_chat", kwargs={"pk": session.pk})
        image = SimpleUploadedFile(
            "work.png",
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 64,
            content_type="image/png",
        )
        response = client.post(
            chat_url,
            {
                "message": "Here is my work",
                "answer_id": str(answer.pk),
                "image": image,
            },
        )
        assert response.status_code == 200
        msg = TutorMessage.objects.filter(
            conversation__student=student,
            conversation__question=question,
            role=TutorMessage.Role.USER,
        ).latest("pk")
        assert msg.image

    def test_tutor_history_filters_by_answer_id(self, client, student, topic, mcq_question):
        question, correct = mcq_question
        wrong_choice = question.choices.filter(is_correct=False).first()
        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
        )
        answer = submit_answer(
            session=session,
            question=question,
            confidence=3,
            selected_choice=wrong_choice,
            time_spent_seconds=10,
        )
        session.status = ReviewSession.Status.COMPLETED
        session.save(update_fields=["status"])

        from apps.reviews.tutor_services import get_or_create_conversation, process_tutor_chat

        process_tutor_chat(session, "Help me understand", answer_id=answer.pk)

        client.force_login(student)
        history_url = reverse("reviews:tutor_history", kwargs={"pk": session.pk})
        response = client.get(history_url + f"?answer_id={answer.pk}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 2
        assert data["active_answer_id"] == answer.pk

    def test_tutor_conversation_cleared_on_retake(self, student, topic, mcq_question):
        question, wrong = mcq_question
        wrong_choice = question.choices.filter(is_correct=False).first()

        session1 = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
        )
        answer1 = submit_answer(
            session=session1,
            question=question,
            confidence=2,
            selected_choice=wrong_choice,
            time_spent_seconds=12,
        )
        session1.status = ReviewSession.Status.COMPLETED
        session1.save(update_fields=["status"])

        from apps.questions.models import ExplanationStep
        from apps.reviews.tutor_services import process_tutor_chat, tutor_history_payload

        ExplanationStep.objects.create(
            question=question,
            order=1,
            content="Step 1: Add the numbers to find the sum.",
        )

        process_tutor_chat(session1, "Explain this", answer_id=answer1.pk)

        session2 = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
        )
        answer2 = submit_answer(
            session=session2,
            question=question,
            confidence=2,
            selected_choice=wrong_choice,
            time_spent_seconds=14,
        )
        session2.status = ReviewSession.Status.COMPLETED
        session2.save(update_fields=["status"])

        payload = tutor_history_payload(session2, answer_id=answer2.pk)
        assert payload["messages"] == []
        item = next(i for i in payload["items"] if i["answer_id"] == answer2.pk)
        assert item["correction_steps"] == [
            "Step 1: Add the numbers to find the sum."
        ]
        assert item["message_count"] == 0

    def test_tutor_history_with_correct_and_wrong_answers(
        self, client, student, topic, mcq_question
    ):
        """Sessions mixing correct and wrong answers must still load tutor history."""
        from apps.questions.models import QuestionChoice

        question1, correct1 = mcq_question

        question2 = Question.objects.create(
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            question_type=Question.QuestionType.MCQ,
            stem="What is 3+3?",
            status=Question.Status.APPROVED,
        )
        correct2 = QuestionChoice.objects.create(
            question=question2, label="A", text="6", is_correct=True
        )
        wrong2 = QuestionChoice.objects.create(
            question=question2, label="B", text="7", is_correct=False
        )

        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=Question.Difficulty.EASY,
            mode=ReviewSession.Mode.TIMED_EXAM,
        )
        submit_answer(
            session=session,
            question=question1,
            confidence=5,
            selected_choice=correct1,
            time_spent_seconds=8,
        )
        submit_answer(
            session=session,
            question=question2,
            confidence=2,
            selected_choice=wrong2,
            time_spent_seconds=10,
        )
        session.status = ReviewSession.Status.COMPLETED
        session.save(update_fields=["status"])

        client.force_login(student)
        history_url = reverse("reviews:tutor_history", kwargs={"pk": session.pk})
        history_response = client.get(history_url)
        assert history_response.status_code == 200
        history_data = history_response.json()
        assert len(history_data["items"]) == 2
        assert any(item["is_correct"] for item in history_data["items"])
        assert any(not item["is_correct"] for item in history_data["items"])

        feedback_url = reverse("reviews:session_generate_feedback", kwargs={"pk": session.pk})
        feedback_response = client.post(feedback_url)
        assert feedback_response.status_code == 200
        feedback_data = feedback_response.json()
        assert len(feedback_data["items"]) == 2
