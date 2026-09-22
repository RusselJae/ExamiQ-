from django.contrib import messages

from django.db import IntegrityError
from django.db.models import Count, Q

from django.http import Http404, HttpResponse, JsonResponse

from django.shortcuts import get_object_or_404, redirect, render

from django.urls import reverse

from django.views import View

from django.views.generic import CreateView, DeleteView, ListView, UpdateView


from apps.ai.factory import (
    get_ai_provider_label,
    get_difficulty_tagger,
    get_question_generator,
    get_question_validator,
)
from apps.ai.exceptions import AIServiceUnavailableError
from apps.ai.normalize import normalize_generated_questions

from apps.core.filtering import (
    STANDARD_DATE_SORT_FILTER_SPECS,
    apply_date_range,
    apply_sort,
    build_filter_fields,
    get_filter_param,
    has_active_filters,
    redirect_preserving_filters,
)
from apps.core.mixins import ProfessorCourseMixin, ProfessorRequiredMixin

from apps.questions.forms import (
    ExplanationStepFormSet,
    QuestionEditForm,
    SimplifiedQuestionChoiceFormSet,
    TopicForm,
)

from apps.questions.models import Question, Subject, Topic
from apps.questions.views_curriculum import (
    CurriculumTopicsView,
    ProfessorCurriculumSubjectsView as ProfessorCurriculumSubjectsAPI,
)
from apps.questions.services import (
    activate_question,
    build_steps_from_post,
    create_question,
    deactivate_question,
    find_duplicate_question,
    mistake_student_threshold,
    question_feedback_summary,
)
from apps.users.assignment_services import (
    get_assigned_subjects_queryset,
    get_or_create_catalog_course,
    get_professor_course_queryset,
    professor_can_access_course,
    professor_can_access_subject,
)
from apps.users.models import Course, User
from apps.questions.validation import validate_question_for_submit


class QuestionListView(ProfessorCourseMixin, ListView):
    model = Question

    template_name = "professor/questions/list.html"

    context_object_name = "questions"

    paginate_by = 25

    def get_queryset(self):

        course_subject = _subject_for_course(self.course)
        queryset = Question.objects.select_related(
            "topic", "topic__subject", "validated_by"
        ).annotate(
            mistake_count=Count("mistake_records"),
            distinct_student_mistake_count=Count(
                "mistake_records__student_id", distinct=True
            ),
        )
        if course_subject:
            queryset = queryset.filter(topic__subject=course_subject)
        else:
            queryset = queryset.none()
        queryset = apply_date_range(queryset, self.request, "created")
        queryset = apply_sort(
            queryset,
            self.request,
            newest_field="-created",
            oldest_field="created",
        )

        search = get_filter_param(self.request, "q")
        if search:
            queryset = queryset.filter(stem__icontains=search)

        topic_id = get_filter_param(self.request, "topic")
        if topic_id.isdigit():
            queryset = queryset.filter(topic_id=int(topic_id))

        subject_id = get_filter_param(self.request, "subject")
        if subject_id.isdigit():
            queryset = queryset.filter(topic__subject_id=int(subject_id))

        difficulty = get_filter_param(self.request, "difficulty")
        if difficulty in Question.Difficulty.values:
            queryset = queryset.filter(difficulty=difficulty)

        question_type = get_filter_param(self.request, "type")
        if question_type in Question.QuestionType.values:
            queryset = queryset.filter(question_type=question_type)

        active = get_filter_param(self.request, "active")
        if active == "yes":
            queryset = queryset.filter(is_active=True)
        elif active == "no":
            queryset = queryset.filter(is_active=False)

        return queryset

    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        context["active_tab"] = "questions"
        context["ai_provider_label"] = get_ai_provider_label()
        context["mistake_student_threshold"] = mistake_student_threshold()
        course_subject = _subject_for_course(self.course)
        q_labels = _question_q_labels_for_subject(course_subject)
        for question in context["questions"]:
            question.q_label = q_labels.get(question.pk, "")
        topics = topics_for_course_subject(self.course, self.request.user)
        filter_names = ["q", "topic", "difficulty", "active", "sort"]
        context["filter_form_fields"] = build_filter_fields(
            self.request,
            [
                {
                    "type": "search",
                    "name": "q",
                    "label": "Search",
                    "placeholder": "Question stem text",
                },
                {
                    "type": "select",
                    "name": "topic",
                    "label": "Topic",
                    "choices": [(str(topic.pk), topic.name) for topic in topics],
                },
                {
                    "type": "select",
                    "name": "difficulty",
                    "label": "Difficulty",
                    "choices": Question.Difficulty.choices,
                },
                {
                    "type": "select",
                    "name": "active",
                    "label": "Status",
                    "choices": [
                        ("yes", "Active"),
                        ("no", "Inactive"),
                    ],
                },
                {
                    "type": "sort",
                    "name": "sort",
                    "label": "Sort",
                    "choices": [
                        ("newest", "Newest first"),
                        ("oldest", "Oldest first"),
                    ],
                },
            ],
        )
        context["filter_has_active"] = has_active_filters(self.request, filter_names)
        context["filter_bar_compact"] = True
        context["filter_bar_single_row"] = True

        return context


class QuestionCreateView(ProfessorCourseMixin, CreateView):
    model = Question

    form_class = QuestionEditForm

    template_name = "professor/questions/form.html"

    def get_form_kwargs(self):

        kwargs = super().get_form_kwargs()

        kwargs["program"] = self.course.program

        return kwargs

    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        if self.request.POST:
            context["choice_formset"] = SimplifiedQuestionChoiceFormSet(
                self.request.POST
            )
            context["step_formset"] = ExplanationStepFormSet(
                self.request.POST, prefix="steps"
            )
        else:
            context["choice_formset"] = SimplifiedQuestionChoiceFormSet()
            context["step_formset"] = ExplanationStepFormSet(prefix="steps")

        context["active_tab"] = "questions"

        context["form_title"] = "Create Question"

        context["is_edit"] = False

        context["mistake_count"] = 0

        from apps.questions.services import clean_adaptive_explanation

        context["adaptive_explanation"] = clean_adaptive_explanation({})

        return context

    def form_valid(self, form):

        context = self.get_context_data()

        choice_formset = context["choice_formset"]
        step_formset = context["step_formset"]
        qtype = form.cleaned_data.get("question_type") or Question.QuestionType.MCQ

        if qtype == Question.QuestionType.MCQ and not choice_formset.is_valid():
            return self.form_invalid(form)
        if not step_formset.is_valid():
            return self.form_invalid(form)

        from apps.questions.services import adaptive_explanation_from_post

        self.object = form.save(commit=False)
        self.object.question_type = qtype
        self.object.status = Question.Status.DRAFT
        self.object.proposed_by = self.request.user
        self.object.explanation_status = "draft"
        self.object.is_active = False
        if qtype != Question.QuestionType.MCQ:
            self.object.correct_answer = None
        self.object.adaptive_explanation = adaptive_explanation_from_post(
            self.request.POST
        )

        self.object.save()

        if qtype == Question.QuestionType.MCQ:
            choice_formset.instance = self.object
            choice_formset.save()
        else:
            self.object.choices.all().delete()

        step_formset.instance = self.object
        step_formset.save()

        from apps.core.audit import log_audit_event
        from apps.core.models import AuditLog

        messages.success(
            self.request,
            "Question saved as draft. Publish it from the question list when ready.",
        )

        log_audit_event(
            self.request.user,
            AuditLog.Action.QUESTION_CREATE,
            message=f"Created question #{self.object.pk}",
            target_type="Question",
            target_id=self.object.pk,
        )

        return redirect(self.get_success_url())

    def get_success_url(self):

        return reverse(
            "analytics_professor:question_list", kwargs={"course_pk": self.course.pk}
        )


class QuestionUpdateView(ProfessorCourseMixin, UpdateView):
    model = Question

    form_class = QuestionEditForm

    template_name = "professor/questions/form.html"

    pk_url_kwarg = "question_pk"

    def get_queryset(self):

        return Question.objects.filter(topic__subject__program=self.course.program)

    def get_form_kwargs(self):

        kwargs = super().get_form_kwargs()

        kwargs["program"] = self.course.program

        return kwargs

    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        if self.request.POST:
            context["choice_formset"] = SimplifiedQuestionChoiceFormSet(
                self.request.POST, instance=self.object
            )
            context["step_formset"] = ExplanationStepFormSet(
                self.request.POST, instance=self.object, prefix="steps"
            )
        else:
            context["choice_formset"] = SimplifiedQuestionChoiceFormSet(
                instance=self.object
            )
            context["step_formset"] = ExplanationStepFormSet(
                instance=self.object, prefix="steps"
            )

        context["active_tab"] = "questions"

        context["form_title"] = "Edit Question"

        context["is_edit"] = True

        from apps.questions.services import (
            prefill_adaptive_explanation,
            question_feedback_summary,
        )

        feedback = question_feedback_summary(self.object)
        context["mistake_count"] = feedback["total_mistakes"]
        context["distinct_student_mistake_count"] = feedback["unique_students"]
        context["mistake_student_threshold"] = feedback["threshold"]
        context["needs_revision"] = feedback["needs_revision"]
        context["feedback_summary"] = feedback
        context["adaptive_explanation"] = prefill_adaptive_explanation(self.object)
        context["regenerate_url"] = reverse(
            "analytics_professor:question_regenerate",
            kwargs={
                "course_pk": self.course.pk,
                "question_pk": self.object.pk,
            },
        )

        return context

    def form_valid(self, form):

        context = self.get_context_data()

        choice_formset = context["choice_formset"]
        step_formset = context["step_formset"]
        qtype = form.cleaned_data.get("question_type") or Question.QuestionType.MCQ

        if qtype == Question.QuestionType.MCQ and not choice_formset.is_valid():
            return self.form_invalid(form)
        if not step_formset.is_valid():
            return self.form_invalid(form)

        from apps.questions.services import adaptive_explanation_from_post

        self.object = form.save(commit=False)
        self.object.question_type = qtype
        if qtype != Question.QuestionType.MCQ:
            self.object.correct_answer = None
        self.object.adaptive_explanation = adaptive_explanation_from_post(
            self.request.POST
        )
        self.object.save()

        if qtype == Question.QuestionType.MCQ:
            choice_formset.instance = self.object
            choice_formset.save()
        else:
            self.object.choices.all().delete()

        step_formset.instance = self.object
        step_formset.save()

        from apps.core.audit import log_audit_event
        from apps.core.models import AuditLog

        log_audit_event(
            self.request.user,
            AuditLog.Action.QUESTION_UPDATE,
            message=f"Updated question #{self.object.pk}",
            target_type="Question",
            target_id=self.object.pk,
        )

        if (
            self.object.status == Question.Status.APPROVED
            and self.object.explanation_steps.exists()
        ):
            from apps.questions.services import approve_question_explanations

            approve_question_explanations(self.object, self.request.user)
            messages.success(
                self.request,
                "Question updated; adaptive explanation and steps saved.",
            )
        else:
            messages.success(
                self.request,
                "Draft updated. Adaptive explanation and steps saved.",
            )

        return redirect(self.get_success_url())

    def get_success_url(self):

        return reverse(
            "analytics_professor:question_list", kwargs={"course_pk": self.course.pk}
        )


class QuestionDeleteView(ProfessorCourseMixin, DeleteView):
    model = Question

    template_name = "professor/questions/confirm_delete.html"

    pk_url_kwarg = "question_pk"

    def get_queryset(self):

        return Question.objects.filter(topic__subject__program=self.course.program)

    def form_valid(self, form):

        deactivate_question(self.object)

        messages.success(self.request, "Question deactivated.")

        return redirect(self.get_success_url())

    def get_success_url(self):

        return reverse(
            "analytics_professor:question_list", kwargs={"course_pk": self.course.pk}
        )

    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        context["active_tab"] = "questions"

        return context


class QuestionToggleActiveView(ProfessorCourseMixin, View):
    def post(self, request, course_pk, question_pk):
        question = get_object_or_404(
            Question.objects.select_related("topic__subject"),
            pk=question_pk,
            topic__subject=_subject_for_course(self.course),
        )
        if question.is_active:
            deactivate_question(question)
            messages.success(request, "Question deactivated.")
        else:
            activate_question(question)
            messages.success(request, "Question activated.")
        return redirect("analytics_professor:question_list", course_pk=course_pk)


class QuestionPublishView(ProfessorCourseMixin, View):
    """Faculty expert attestation: publish a draft question for students."""

    def post(self, request, course_pk, question_pk):
        from apps.questions.services import publish_question_as_faculty

        subject = _subject_for_course(self.course)
        question = get_object_or_404(
            Question.objects.select_related("topic__subject"),
            pk=question_pk,
            topic__subject=subject,
        )
        if request.POST.get("faculty_attest") != "1":
            messages.error(
                request,
                "Confirm faculty attestation before publishing this question.",
            )
            return redirect("analytics_professor:question_edit", course_pk=course_pk, question_pk=question_pk)
        publish_question_as_faculty(
            question,
            request.user,
            approve_explanations=request.POST.get("approve_explanations") == "1",
        )
        messages.success(request, "Question published after faculty attestation.")
        return redirect("analytics_professor:question_list", course_pk=course_pk)


class QuestionSuggestDifficultyView(ProfessorCourseMixin, View):
    def post(self, request, course_pk):

        stem = request.POST.get("stem", "")

        current = request.POST.get("difficulty", Question.Difficulty.MEDIUM)

        suggested = get_difficulty_tagger().tag(stem, current)

        return render(
            request,
            "professor/questions/partials/difficulty_suggestion.html",
            {"difficulty": suggested},
        )


class ProfessorCurriculumSubjectsView(
    ProfessorCourseMixin, ProfessorCurriculumSubjectsAPI
):
    def get(self, request, course_pk):
        request.GET = request.GET.copy()
        request.GET["program"] = str(self.course.program_id)
        return super().get(request, program_slug=self.course.program.slug)


class ProfessorCurriculumTopicsView(ProfessorCourseMixin, CurriculumTopicsView):
    def get(self, request, course_pk):
        return super().get(request)


class QuestionBatchEditView(ProfessorCourseMixin, View):
    """Dedicated edit page for a batch draft question (client-side sessionStorage)."""

    template_name = "professor/questions/batch_question_edit.html"

    def get(self, request, course_pk, question_index):
        return render(
            request,
            self.template_name,
            {
                "course": self.course,
                "active_tab": "questions",
                "form_title": "Edit Question",
                "question_index": question_index,
                "question_number": question_index + 1,
            },
        )


class QuestionBatchCreateView(ProfessorCourseMixin, View):
    """Batch question builder with AI generate/validate workflow."""

    template_name = "professor/questions/batch_form.html"

    def get_context_data(self):
        from apps.ai.material_services import ready_documents_for_course

        topics = topics_for_course_section(self.course, self.request.user)
        subject = _subject_for_course(self.course)
        return {
            "course": self.course,
            "active_tab": "questions",
            "form_title": "Add Questions",
            "topics": topics,
            "course_subject": subject,
            "learning_documents": ready_documents_for_course(self.course.pk),
            "difficulty_choices": [
                (Question.Difficulty.EASY, "Beginner"),
                (Question.Difficulty.MEDIUM, "Intermediate"),
                (Question.Difficulty.HARD, "Advanced"),
            ],
            "question_type_choices": list(Question.AUTHORABLE_QUESTION_TYPE_CHOICES),
            "ai_provider_label": get_ai_provider_label(),
        }

    def get(self, request, course_pk):
        return render(request, self.template_name, self.get_context_data())

    def post(self, request, course_pk):
        topic_id = request.POST.get("topic")
        difficulty = request.POST.get("difficulty", Question.Difficulty.MEDIUM)
        topic = (
            topics_for_course_section(self.course, request.user)
            .filter(pk=topic_id)
            .first()
        )
        if not topic:
            messages.error(request, "Select a valid topic before submitting.")
            return render(request, self.template_name, self.get_context_data())

        try:
            count = int(request.POST.get("question_count", 0))
        except (TypeError, ValueError):
            count = 0

        created = 0
        skipped_invalid = 0
        skipped_duplicates: list[str] = []
        seen_stems: set[str] = set()
        explanation_question_ids: list[int] = []
        published_ids: list[int] = []

        from apps.questions.services import publish_question_as_faculty

        valid_difficulties = {c.value for c in Question.Difficulty}
        valid_types = set(Question.AUTHORABLE_QUESTION_TYPES)

        for index in range(count):
            stem = request.POST.get(f"stem_{index}", "").strip()
            if not stem:
                continue
            concept_tag = request.POST.get(f"concept_tag_{index}", "").strip()
            question_type = request.POST.get(
                f"question_type_{index}", Question.QuestionType.MCQ
            )
            if question_type not in valid_types:
                question_type = Question.QuestionType.MCQ
            expected_answer = request.POST.get(f"expected_answer_{index}", "").strip()
            skip_ai_gate = request.POST.get(f"ai_generated_{index}", "") == "1"
            correct_label = request.POST.get(f"correct_{index}", "A").upper()
            row_difficulty = request.POST.get(f"difficulty_{index}", difficulty)
            if row_difficulty not in valid_difficulties:
                row_difficulty = (
                    difficulty
                    if difficulty in valid_difficulties
                    else Question.Difficulty.MEDIUM
                )
            choices_data = []
            if question_type == Question.QuestionType.MCQ:
                for label in ("A", "B", "C", "D"):
                    text = request.POST.get(f"choice_{index}_{label}", "").strip()
                    if text:
                        choices_data.append(
                            {
                                "label": label,
                                "text": text,
                                "is_correct": label == correct_label,
                            }
                        )

            validation = validate_question_for_submit(
                stem,
                choices_data,
                topic,
                row_difficulty,
                correct_label,
                ai_enabled=False,
                question_type=question_type,
                expected_answer=expected_answer,
            )
            if not validation.get("is_valid"):
                skipped_invalid += 1
                continue

            normalized = find_duplicate_question(topic.pk, stem)
            if normalized:
                skipped_duplicates.append(stem[:60])
                continue

            from apps.questions.services import normalize_stem

            stem_key = normalize_stem(stem)
            if stem_key in seen_stems:
                skipped_duplicates.append(stem[:60])
                continue
            seen_stems.add(stem_key)

            steps_raw = request.POST.get(f"steps_{index}", "")
            solution_summary = request.POST.get(f"solution_summary_{index}", "")
            faculty_attest = request.POST.get(f"faculty_attest_{index}") == "1"
            adaptive_raw = request.POST.get(f"adaptive_explanation_{index}", "")
            from apps.questions.services import clean_adaptive_explanation

            adaptive_explanation: dict = {}
            if adaptive_raw.strip():
                import json

                try:
                    parsed = json.loads(adaptive_raw)
                    if isinstance(parsed, dict):
                        adaptive_explanation = clean_adaptive_explanation(parsed)
                except (json.JSONDecodeError, TypeError):
                    adaptive_explanation = {}
            # AI drafts defer explanations to a background job; do not invent
            # steps from concept_tag alone.
            if skip_ai_gate and not steps_raw.strip() and not solution_summary.strip():
                steps = []
            else:
                steps = build_steps_from_post(
                    steps_raw,
                    concept_tag=concept_tag,
                    solution_summary=solution_summary,
                )
            question_payload = {
                "topic": topic,
                "difficulty": row_difficulty,
                "question_type": question_type,
                "stem": stem,
                "concept_tag": concept_tag,
                "expected_answer": (
                    expected_answer
                    if question_type != Question.QuestionType.MCQ
                    else ""
                ),
                "is_active": faculty_attest,
                "status": Question.Status.DRAFT,
                "proposed_by": request.user,
                "explanation_status": "draft",
                "adaptive_explanation": adaptive_explanation,
            }

            question = create_question(
                question_payload,
                choices_data if question_type == Question.QuestionType.MCQ else [],
                steps,
            )
            if faculty_attest:
                publish_question_as_faculty(
                    question,
                    request.user,
                    approve_explanations=True,
                )
                published_ids.append(question.pk)
            if skip_ai_gate and not steps:
                explanation_question_ids.append(question.pk)
            # ai_generated flag is client-side only (skip_ai_gate used at validate time)
            _ = skip_ai_gate
            from apps.core.audit import log_audit_event
            from apps.core.models import AuditLog

            log_audit_event(
                request.user,
                AuditLog.Action.QUESTION_CREATE,
                message=f"Created question #{question.pk}",
                target_type="Question",
                target_id=question.pk,
            )
            created += 1

        if skipped_invalid:
            messages.error(
                request,
                f"Skipped {skipped_invalid} invalid question(s). Fix and validate before submitting.",
            )
        if skipped_duplicates:
            messages.warning(
                request,
                "Skipped duplicate question(s) already in the bank or queue: "
                + "; ".join(skipped_duplicates[:3])
                + ("…" if len(skipped_duplicates) > 3 else ""),
            )
        if created:
            explanation_job = None
            if explanation_question_ids:
                from apps.ai.job_services import start_explanation_generation_job

                explanation_job = start_explanation_generation_job(
                    user=request.user,
                    course_id=self.course.pk,
                    topic_id=topic.pk,
                    question_ids=explanation_question_ids,
                )
            if explanation_job:
                messages.success(
                    request,
                    f"Saved {created} question(s). Explanations are generating in the background.",
                )
            elif published_ids:
                messages.success(
                    request,
                    f"Published {len(published_ids)} question(s) after faculty attestation.",
                )
            else:
                messages.success(
                    request,
                    f"Saved {created} draft question(s). Attest and publish when ready for students.",
                )
            return redirect(
                "analytics_professor:question_list", course_pk=self.course.pk
            )
        if not skipped_invalid and not skipped_duplicates:
            messages.warning(
                request, "No questions were saved. Add at least one complete question."
            )
        return render(request, self.template_name, self.get_context_data())


class QuestionCSVImportView(ProfessorCourseMixin, View):
    """Import questions from a CSV file on the Add Questions screen."""

    def post(self, request, course_pk):
        from apps.core.audit import log_audit_event
        from apps.core.models import AuditLog
        from apps.questions.import_services import (
            ImportFormatError,
            import_questions_from_csv,
        )

        uploaded = request.FILES.get("csv_file")
        if not uploaded:
            return JsonResponse({"error": "Upload a CSV file to import."}, status=400)

        subject = _subject_for_course(self.course)
        if not subject:
            return JsonResponse(
                {"error": "Link a subject to this course before importing."},
                status=400,
            )

        try:
            summary = import_questions_from_csv(
                uploaded,
                subject=subject,
                professor=request.user,
            )
        except ImportFormatError as exc:
            return JsonResponse({"error": str(exc)}, status=400)

        if summary.created:
            log_audit_event(
                request.user,
                AuditLog.Action.QUESTION_CREATE,
                message=f"Imported {summary.created} question(s) from CSV",
                target_type="Question",
                target_id=subject.pk,
            )
            messages.success(
                request,
                f"Imported {summary.created} question(s) from CSV.",
            )
        if summary.skipped_invalid:
            messages.warning(
                request,
                f"Skipped {summary.skipped_invalid} invalid row(s). Check the import summary.",
            )
        if summary.skipped_duplicates:
            messages.warning(
                request,
                f"Skipped {summary.skipped_duplicates} duplicate row(s).",
            )

        payload = summary.to_dict()
        payload["redirect_url"] = reverse(
            "analytics_professor:question_list",
            kwargs={"course_pk": self.course.pk},
        )
        return JsonResponse(payload)


def _hub_course_options(professor):
    """Course subject options for the top-level Add Questions filter."""
    subjects = (
        Subject.objects.filter(program__slug=User.HomeDegreeProgram.BSED_MATH)
        .select_related("program", "year_level")
        .order_by("year_level__order", "semester", "code")
    )
    options = []
    for subject in subjects:
        course = get_or_create_catalog_course(professor, subject)
        options.append(
            {
                "course": course,
                "subject": subject,
                "label": f"{subject.code} — {subject.name}",
            }
        )
    return options


class QuestionAddHubView(ProfessorRequiredMixin, View):
    """Top-level Add Questions entry with course-subject filter."""

    template_name = "professor/questions/batch_form.html"

    def get(self, request):
        course_options = _hub_course_options(request.user)
        course_pk = request.GET.get("course", "")
        if course_pk.isdigit():
            course = get_object_or_404(Course, pk=int(course_pk))
            if not professor_can_access_course(request.user, course):
                raise Http404()
            batch_view = QuestionBatchCreateView()
            batch_view.request = request
            batch_view.course = course
            batch_view.kwargs = {"course_pk": course.pk}
            context = batch_view.get_context_data()
            context.update(
                {
                    "hub_mode": True,
                    "hub_subject_selected": True,
                    "form_action": reverse(
                        "analytics_professor:question_create",
                        kwargs={"course_pk": course.pk},
                    ),
                    "course_options": course_options,
                    "selected_course_pk": course.pk,
                }
            )
            return render(request, self.template_name, context)

        return render(
            request,
            self.template_name,
            {
                "hub_mode": True,
                "hub_subject_selected": False,
                "form_title": "Add Questions",
                "form_action": "#",
                "course": None,
                "topics": [],
                "course_subject": None,
                "difficulty_choices": [
                    (Question.Difficulty.EASY, "Beginner"),
                    (Question.Difficulty.MEDIUM, "Intermediate"),
                    (Question.Difficulty.HARD, "Advanced"),
                ],
                "question_type_choices": list(Question.AUTHORABLE_QUESTION_TYPE_CHOICES),
                "course_options": course_options,
                "selected_course_pk": None,
                "learning_documents": [],
                "ai_provider_label": get_ai_provider_label(),
            },
        )


class QuestionAIGenerateView(ProfessorCourseMixin, View):
    """Enqueue AI question generation and return a job id for polling."""

    def post(self, request, course_pk):
        from apps.ai.job_services import start_question_generation_job
        from apps.ai.retrieval import (
            retrieve_material_for_topic,
            sample_material_for_relevance,
        )
        from apps.ai.source_extract import SourceMaterialError
        from apps.ai.subject_relevance import assess_subject_relevance

        difficulty = request.POST.get("difficulty", Question.Difficulty.EASY)
        question_type = Question.QuestionType.MCQ
        try:
            count = int(request.POST.get("count") or 3)
        except (TypeError, ValueError):
            count = 3
        from django.conf import settings as django_settings

        max_count = int(getattr(django_settings, "AI_GENERATION_MAX_COUNT", 50) or 50)
        count = max(1, count)
        if max_count > 0:
            count = min(count, max_count)

        subject = _subject_for_course(self.course)
        if not subject:
            return JsonResponse(
                {"error": "Link a subject to this course before generating."},
                status=400,
            )
        topics = list(
            topics_for_course_section(self.course, request.user).select_related(
                "subject"
            )
        )
        if not topics:
            return JsonResponse(
                {"error": "Create at least one topic under this course subject first."},
                status=400,
            )

        uploaded = request.FILES.get("source_file")
        library_id = request.POST.get("learning_document_id") or request.POST.get("material")
        document = None
        if library_id:
            from apps.ai.models import LearningDocument

            document = LearningDocument.objects.filter(
                pk=library_id,
                course_id=self.course.pk,
                status=LearningDocument.Status.READY,
                is_archived=False,
            ).first()
            if document is None:
                return JsonResponse(
                    {"error": "Selected learning material was not found or is not ready."},
                    status=400,
                )
        elif uploaded:
            try:
                from apps.ai.material_services import ingest_course_material

                document = ingest_course_material(
                    uploaded_file=uploaded,
                    course_id=self.course.pk,
                    user=request.user,
                    subject=subject,
                )
            except SourceMaterialError as exc:
                return JsonResponse({"error": str(exc)}, status=400)
        else:
            return JsonResponse(
                {
                    "error": "Upload a module or pick a saved learning material to generate questions."
                },
                status=400,
            )

        sample = sample_material_for_relevance(document)
        relevance = assess_subject_relevance(sample, subject, topics)
        if not relevance["related"]:
            return JsonResponse(
                {
                    "error": relevance.get("reason")
                    or "Uploaded module is not related to this course subject.",
                    "relevance_blocked": True,
                    "reason": relevance.get("reason")
                    or "Uploaded module is not related to this course subject.",
                    "subject_score": relevance.get("subject_score", 0),
                    "topic_score": relevance.get("topic_score", 0),
                },
                status=400,
            )

        topic_id = relevance.get("matched_topic_id") or request.POST.get("topic")
        try:
            topic_id = int(topic_id) if topic_id is not None else None
        except (TypeError, ValueError):
            topic_id = None
        topic = (
            next((t for t in topics if t.pk == topic_id), None) if topic_id else None
        )
        if topic is None:
            topic = topics[0]

        source_material = retrieve_material_for_topic(document=document, topic=topic)
        if not source_material:
            source_material = sample
        if not source_material:
            return JsonResponse(
                {"error": "Could not read enough text from the uploaded module."},
                status=400,
            )

        job = start_question_generation_job(
            user=request.user,
            course_id=self.course.pk,
            topic_id=topic.pk,
            difficulty=difficulty,
            count=count,
            source_material=source_material,
            learning_document=document,
            question_type=question_type,
        )
        return JsonResponse(
            {
                "job_id": job.pk,
                "status": job.status,
                "topic_id": topic.pk,
                "status_url": reverse(
                    "analytics_professor:question_ai_generate_status",
                    kwargs={"course_pk": self.course.pk, "job_id": job.pk},
                ),
            },
            status=202,
        )


class QuestionRegenerateView(ProfessorCourseMixin, View):
    """Regenerate easier/clearer variations of a high-mistake question."""

    def post(self, request, course_pk, question_pk):
        from apps.ai.job_services import start_question_generation_job
        from apps.ai.material_services import ready_documents_for_course
        from apps.ai.retrieval import retrieve_material_for_topic
        from apps.questions.services import (
            mistake_student_threshold,
            question_needs_revision,
        )

        question = get_object_or_404(
            Question.objects.select_related("topic", "topic__subject"),
            pk=question_pk,
            topic__subject__program=self.course.program,
        )
        if not question_needs_revision(question):
            return JsonResponse(
                {
                    "error": (
                        f"Regenerate unlocks after "
                        f"{mistake_student_threshold()} distinct students miss this question."
                    )
                },
                status=400,
            )

        topic = question.topic
        source_material = ""
        document = None
        for doc in ready_documents_for_course(self.course.pk):
            source_material = retrieve_material_for_topic(document=doc, topic=topic)
            if source_material:
                document = doc
                break
        if not source_material:
            source_material = "\n".join(
                part
                for part in [
                    f"Concept: {question.concept_tag}" if question.concept_tag else "",
                    f"Current question:\n{question.stem}",
                ]
                if part
            )

        job = start_question_generation_job(
            user=request.user,
            course_id=self.course.pk,
            topic_id=topic.pk,
            difficulty=question.difficulty,
            count=3,
            source_material=source_material,
            learning_document=document,
            question_type=question.question_type or Question.QuestionType.MCQ,
            reference_stem=question.stem,
            reference_question_id=question.pk,
        )
        return JsonResponse(
            {
                "job_id": job.pk,
                "status": job.status,
                "topic_id": topic.pk,
                "status_url": reverse(
                    "analytics_professor:question_ai_generate_status",
                    kwargs={"course_pk": self.course.pk, "job_id": job.pk},
                ),
            },
            status=202,
        )


class QuestionAIGenerateStatusView(ProfessorCourseMixin, View):
    """Poll job status; return JSON while running, HTML modal when finished."""

    def get(self, request, course_pk, job_id):
        from apps.ai.models import AIGenerationJob

        job = get_object_or_404(
            AIGenerationJob,
            pk=job_id,
            created_by=request.user,
            course_id=self.course.pk,
            job_type=AIGenerationJob.JobType.QUESTION_GENERATE,
        )
        topic = Topic.objects.filter(pk=job.topic_id).first()
        if job.status in (
            AIGenerationJob.Status.PENDING,
            AIGenerationJob.Status.RUNNING,
        ):
            written = len((job.result or {}).get("variations") or [])
            return JsonResponse(
                {
                    "job_id": job.pk,
                    "status": job.status,
                    "done": False,
                    "written": written,
                    "count": job.count,
                }
            )

        variations = []
        if job.status == AIGenerationJob.Status.SUCCEEDED:
            variations = normalize_generated_questions(
                job.result.get("variations") or [],
                question_type=job.question_type,
            )

        wants_json = "application/json" in (request.headers.get("Accept") or "")
        if wants_json and request.GET.get("html") != "1":
            return JsonResponse(
                {
                    "job_id": job.pk,
                    "status": job.status,
                    "done": True,
                    "error": job.error_message or None,
                    "variations": variations,
                }
            )

        return render(
            request,
            "professor/questions/partials/generate_modal.html",
            {
                "variations": variations,
                "course": self.course,
                "topic": topic,
                "difficulty": job.difficulty or Question.Difficulty.EASY,
                "question_type": job.question_type or Question.QuestionType.MCQ,
                "ai_error": job.error_message or None,
            },
        )


class QuestionAIValidateView(ProfessorCourseMixin, View):
    def post(self, request, course_pk):
        import json

        topic_id = request.POST.get("topic")
        difficulty = request.POST.get("difficulty", Question.Difficulty.EASY)
        stem = request.POST.get("stem", "")
        correct_label = request.POST.get("correct_label", "A").upper()
        question_type = Question.QuestionType.MCQ
        expected_answer = request.POST.get("expected_answer", "").strip()
        topic = (
            topics_for_course_section(self.course, request.user)
            .filter(pk=topic_id)
            .select_related("subject")
            .first()
        )
        if not topic:
            return HttpResponse("Select a topic first.", status=400)

        choices = []
        if question_type == Question.QuestionType.MCQ:
            for label in ("A", "B", "C", "D"):
                text = request.POST.get(f"choice_{label}", "").strip()
                if text:
                    choices.append(
                        {
                            "label": label,
                            "text": text,
                            "is_correct": label == correct_label,
                        }
                    )

        peer_stems = []
        raw_peer_stems = request.POST.get("peer_stems", "")
        if raw_peer_stems:
            try:
                parsed = json.loads(raw_peer_stems)
                if isinstance(parsed, list):
                    peer_stems = [str(item) for item in parsed]
            except (TypeError, ValueError):
                peer_stems = []

        result = validate_question_for_submit(
            stem,
            choices,
            topic,
            difficulty,
            correct_label,
            peer_stems=peer_stems,
            question_type=question_type,
            expected_answer=expected_answer,
        )

        if "application/json" in request.headers.get("Accept", ""):
            return JsonResponse(result)

        return render(
            request,
            "professor/questions/partials/validate_modal.html",
            {"result": result, "course": self.course},
        )


class QuestionAIDetectTopicsView(ProfessorCourseMixin, View):
    """Detect math topics/branches from an uploaded learning module."""

    def post(self, request, course_pk):
        from apps.ai.ingest import ingest_learning_upload
        from apps.ai.retrieval import sample_material_for_detection
        from apps.ai.source_extract import SourceMaterialError
        from apps.ai.topic_detect import detect_topics_from_material

        uploaded = request.FILES.get("source_file")
        if not uploaded:
            return JsonResponse(
                {"error": "Upload a module file to detect topics."},
                status=400,
            )
        try:
            document = ingest_learning_upload(
                uploaded_file=uploaded,
                course_id=self.course.pk,
                user=request.user,
            )
        except SourceMaterialError as exc:
            return JsonResponse({"error": str(exc)}, status=400)

        source_material = sample_material_for_detection(document)
        if not source_material:
            return JsonResponse(
                {"error": "Could not extract enough text to detect topics."},
                status=400,
            )

        existing_topics = list(
            topics_for_course_section(self.course, request.user).values("id", "name")
        )
        result = detect_topics_from_material(source_material, existing_topics)
        result["document_id"] = document.pk
        return JsonResponse(result)


def _get_program_subject(course, subject_id, professor=None):
    if not subject_id or not str(subject_id).isdigit():
        return None
    subject = Subject.objects.filter(
        pk=int(subject_id),
        program=course.program,
    ).first()
    if (
        subject
        and professor
        and not professor_can_access_subject(professor, subject, course=course)
    ):
        return None
    return subject


def _subject_for_course(course):
    """Resolve the curriculum subject bound to a faculty course offering."""
    assignment = getattr(course, "teaching_assignment", None)
    if assignment and assignment.subject_id:
        return assignment.subject
    return Subject.objects.filter(
        code=course.code,
        program=course.program,
    ).first()


def _question_q_labels_for_subject(subject) -> dict[int, str]:
    """Map question pk → Q1…Qn by creation order within a subject."""
    if subject is None:
        return {}
    return {
        qid: f"Q{index}"
        for index, qid in enumerate(
            Question.objects.filter(topic__subject=subject)
            .order_by("pk")
            .values_list("pk", flat=True),
            start=1,
        )
    }


def subjects_for_course_section(course, professor=None):
    """All curriculum subjects for courses sharing this section label."""
    section = (course.section or "").strip()
    if professor is not None:
        section_courses = get_professor_course_queryset(professor)
    else:
        section_courses = Course.objects.filter(
            professor_id=course.professor_id,
            is_archived=False,
        )
    if section:
        section_courses = section_courses.filter(section=section)
    else:
        section_courses = section_courses.filter(pk=course.pk)

    subject_ids: set[int] = set()
    for offering in section_courses.select_related("teaching_assignment__subject"):
        subject = _subject_for_course(offering)
        if subject:
            subject_ids.add(subject.pk)
    if not subject_ids:
        return Subject.objects.none()
    return Subject.objects.filter(pk__in=subject_ids)


def topics_for_course_subject(course, professor=None):
    """Top-level topics for the curriculum subject bound to this course only."""
    subject = _subject_for_course(course)
    if not subject:
        return Topic.objects.none()
    if professor is not None and not professor_can_access_subject(
        professor, subject, course=course
    ):
        return Topic.objects.none()
    return (
        Topic.objects.filter(subject=subject, parent__isnull=True)
        .select_related("subject")
        .order_by("name")
    )


def topics_for_course_section(course, professor=None):
    """Deprecated alias — course tools are subject-scoped."""
    return topics_for_course_subject(course, professor)


class TopicListView(ProfessorCourseMixin, ListView):
    model = Topic
    template_name = "professor/topics/list.html"
    context_object_name = "topics"

    def get_queryset(self):
        return topics_for_course_section(self.course, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "topics"
        context["course_subject"] = _subject_for_course(self.course)
        return context


class TopicCreateView(ProfessorCourseMixin, View):
    def post(self, request, course_pk):
        wants_json = "application/json" in (request.headers.get("Accept") or "")
        subject = _subject_for_course(self.course)
        if not subject:
            if wants_json:
                return JsonResponse(
                    {"error": "This course has no linked subject."},
                    status=400,
                )
            messages.error(request, "This course has no linked subject.")
            return redirect(
                reverse(
                    "analytics_professor:topic_list", kwargs={"course_pk": course_pk}
                )
            )
        form = TopicForm(request.POST)
        if form.is_valid():
            topic = form.save(commit=False)
            topic.subject = subject
            try:
                topic.save()
                if wants_json:
                    return JsonResponse(
                        {"id": topic.pk, "name": topic.name},
                        status=201,
                    )
                messages.success(request, f'Topic "{topic.name}" added.')
            except IntegrityError:
                if wants_json:
                    return JsonResponse(
                        {
                            "error": "A topic with this name already exists for this course."
                        },
                        status=400,
                    )
                messages.error(
                    request, "A topic with this name already exists for this course."
                )
        else:
            if wants_json:
                return JsonResponse({"error": "Enter a valid topic name."}, status=400)
            messages.error(request, "Enter a valid topic name.")
        return redirect(
            reverse("analytics_professor:topic_list", kwargs={"course_pk": course_pk})
        )


class TopicUpdateView(ProfessorCourseMixin, View):
    def post(self, request, course_pk, topic_pk):
        topic = get_object_or_404(
            topics_for_course_section(self.course, request.user),
            pk=topic_pk,
        )
        form = TopicForm(request.POST, instance=topic)
        if form.is_valid():
            form.save()
            messages.success(request, "Topic updated.")
        else:
            messages.error(request, "Enter a valid topic name.")
        return redirect(
            reverse("analytics_professor:topic_list", kwargs={"course_pk": course_pk})
        )


class TopicDeleteView(ProfessorCourseMixin, View):
    def post(self, request, course_pk, topic_pk):
        topic = get_object_or_404(
            topics_for_course_section(self.course, request.user),
            pk=topic_pk,
        )
        if topic.questions.exists():
            messages.error(
                request,
                "Cannot delete this topic — it has linked questions.",
            )
        else:
            topic.delete()
            messages.success(request, "Topic deleted.")
        return redirect(
            reverse("analytics_professor:topic_list", kwargs={"course_pk": course_pk})
        )
