from django.contrib import messages

from django.db import IntegrityError
from django.db.models import Count, Q

from django.http import HttpResponse, JsonResponse

from django.shortcuts import get_object_or_404, redirect, render

from django.urls import reverse

from django.views import View

from django.views.generic import CreateView, DeleteView, ListView, UpdateView



from apps.ai.factory import get_ai_provider_label, get_difficulty_tagger, get_question_generator, get_question_validator
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
from apps.core.mixins import ProfessorCourseMixin

from apps.questions.forms import (
    QuestionEditForm,
    SimplifiedQuestionChoiceFormSet,
    TopicForm,
)

from apps.questions.models import Question, Subject, Topic, YearLevel
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
)
from apps.users.assignment_services import (
    get_assigned_subjects_queryset,
    professor_can_access_subject,
)
from apps.questions.validation import validate_question_for_submit





class QuestionListView(ProfessorCourseMixin, ListView):

    model = Question

    template_name = "professor/questions/list.html"

    context_object_name = "questions"

    paginate_by = 25



    def get_queryset(self):

        queryset = (
            Question.objects.filter(topic__subject__program=self.course.program)
            .select_related("topic", "topic__subject")
            .annotate(mistake_count=Count("mistake_records"))
        )
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
        topics = Topic.objects.filter(subject__program=self.course.program).order_by("name")
        subjects = get_assigned_subjects_queryset(
            self.request.user, self.course.program_id
        ).order_by("code")
        filter_names = ["q", "topic", "subject", "difficulty", "type", "active", "date_from", "date_to", "sort"]
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
                    "name": "subject",
                    "label": "Course",
                    "choices": [(str(s.pk), s.name) for s in subjects],
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
                    "name": "type",
                    "label": "Type",
                    "choices": Question.QuestionType.choices,
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
                *STANDARD_DATE_SORT_FILTER_SPECS,
            ],
        )
        context["filter_has_active"] = has_active_filters(self.request, filter_names)

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

            context["choice_formset"] = SimplifiedQuestionChoiceFormSet(self.request.POST)

        else:

            context["choice_formset"] = SimplifiedQuestionChoiceFormSet()

        context["active_tab"] = "questions"

        context["form_title"] = "Create Question"

        context["is_edit"] = False

        context["mistake_count"] = 0

        return context



    def form_valid(self, form):

        context = self.get_context_data()

        choice_formset = context["choice_formset"]

        if not choice_formset.is_valid():

            return self.form_invalid(form)

        self.object = form.save(commit=False)

        self.object.question_type = Question.QuestionType.MCQ

        self.object.status = Question.Status.APPROVED

        self.object.proposed_by = self.request.user

        self.object.save()

        choice_formset.instance = self.object

        choice_formset.save()

        from apps.core.audit import log_audit_event
        from apps.core.models import AuditLog

        log_audit_event(
            self.request.user,
            AuditLog.Action.QUESTION_CREATE,
            message=f"Created question #{self.object.pk}",
            target_type="Question",
            target_id=self.object.pk,
        )

        messages.success(self.request, "Question saved and published.")

        return redirect(self.get_success_url())



    def get_success_url(self):

        return reverse("analytics_professor:question_list", kwargs={"course_pk": self.course.pk})





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

        else:

            context["choice_formset"] = SimplifiedQuestionChoiceFormSet(instance=self.object)

        context["active_tab"] = "questions"

        context["form_title"] = "Edit Question"

        context["is_edit"] = True

        context["mistake_count"] = self.object.mistake_records.count()

        return context



    def form_valid(self, form):

        context = self.get_context_data()

        choice_formset = context["choice_formset"]

        if not choice_formset.is_valid():

            return self.form_invalid(form)

        self.object = form.save()

        choice_formset.save()

        from apps.core.audit import log_audit_event
        from apps.core.models import AuditLog

        log_audit_event(
            self.request.user,
            AuditLog.Action.QUESTION_UPDATE,
            message=f"Updated question #{self.object.pk}",
            target_type="Question",
            target_id=self.object.pk,
        )

        messages.success(self.request, "Question updated.")

        return redirect(self.get_success_url())



    def get_success_url(self):

        return reverse("analytics_professor:question_list", kwargs={"course_pk": self.course.pk})





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

        return reverse("analytics_professor:question_list", kwargs={"course_pk": self.course.pk})



    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        context["active_tab"] = "questions"

        return context




class QuestionToggleActiveView(ProfessorCourseMixin, View):
    """Toggle question is_active without a confirmation page."""

    def post(self, request, course_pk, question_pk):
        question = get_object_or_404(
            Question,
            pk=question_pk,
            topic__subject__program=self.course.program,
        )
        was_active = question.is_active
        if was_active:
            deactivate_question(question)
            messages.success(request, "Question deactivated.")
        else:
            activate_question(question)
            messages.success(request, "Question reactivated.")
        from apps.core.audit import log_audit_event
        from apps.core.models import AuditLog

        log_audit_event(
            request.user,
            AuditLog.Action.QUESTION_TOGGLE,
            message=f"{'Deactivated' if was_active else 'Reactivated'} question #{question.pk}",
            target_type="Question",
            target_id=question.pk,
        )
        return redirect_preserving_filters(
            request,
            "analytics_professor:question_list",
            course_pk=self.course.pk,
        )




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




class ProfessorCurriculumSubjectsView(ProfessorCourseMixin, ProfessorCurriculumSubjectsAPI):
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
        year_levels = YearLevel.objects.all()
        subjects = get_assigned_subjects_queryset(
            self.request.user, self.course.program_id
        ).select_related("year_level")
        return {
            "course": self.course,
            "active_tab": "questions",
            "form_title": "Add Questions",
            "year_levels": year_levels,
            "subjects": subjects,
            "program": self.course.program,
            "difficulty_choices": [
                (Question.Difficulty.EASY, "Beginner"),
                (Question.Difficulty.MEDIUM, "Intermediate"),
                (Question.Difficulty.HARD, "Advanced"),
            ],
            "ai_provider_label": get_ai_provider_label(),
        }

    def get(self, request, course_pk):
        return render(request, self.template_name, self.get_context_data())

    def post(self, request, course_pk):
        topic_id = request.POST.get("topic")
        difficulty = request.POST.get("difficulty", Question.Difficulty.MEDIUM)
        topic = Topic.objects.filter(
            pk=topic_id,
            subject__program=self.course.program,
        ).first()
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

        for index in range(count):
            stem = request.POST.get(f"stem_{index}", "").strip()
            if not stem:
                continue
            concept_tag = request.POST.get(f"concept_tag_{index}", "").strip()
            correct_label = request.POST.get(f"correct_{index}", "A").upper()
            choices_data = []
            for label in ("A", "B", "C", "D"):
                text = request.POST.get(f"choice_{index}_{label}", "").strip()
                if text:
                    choices_data.append({
                        "label": label,
                        "text": text,
                        "is_correct": label == correct_label,
                    })

            validation = validate_question_for_submit(
                stem, choices_data, topic, difficulty, correct_label, ai_enabled=False
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

            steps = build_steps_from_post(
                request.POST.get(f"steps_{index}", ""),
                concept_tag=concept_tag,
                solution_summary=request.POST.get(f"solution_summary_{index}", ""),
            )
            question = create_question(
                {
                    "topic": topic,
                    "difficulty": difficulty,
                    "question_type": Question.QuestionType.MCQ,
                    "stem": stem,
                    "concept_tag": concept_tag,
                    "is_active": True,
                    "status": Question.Status.APPROVED,
                    "proposed_by": request.user,
                },
                choices_data,
                steps,
            )
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
            messages.success(request, f"Saved {created} question(s) to the question bank.")
            return redirect("analytics_professor:question_list", course_pk=self.course.pk)
        if not skipped_invalid and not skipped_duplicates:
            messages.warning(request, "No questions were saved. Add at least one complete question.")
        return render(request, self.template_name, self.get_context_data())


class QuestionAIGenerateView(ProfessorCourseMixin, View):
    """Enqueue AI question generation and return a job id for polling."""

    def post(self, request, course_pk):
        from apps.ai.job_services import start_question_generation_job

        topic_id = request.POST.get("topic")
        difficulty = request.POST.get("difficulty", Question.Difficulty.EASY)
        try:
            count = int(request.POST.get("count") or 3)
        except (TypeError, ValueError):
            count = 3
        topic = Topic.objects.filter(
            pk=topic_id,
            subject__program=self.course.program,
        ).select_related("subject").first()
        if not topic:
            return JsonResponse({"error": "Select a topic first."}, status=400)

        job = start_question_generation_job(
            user=request.user,
            course_id=self.course.pk,
            topic_id=topic.pk,
            difficulty=difficulty,
            count=count,
        )
        return JsonResponse(
            {
                "job_id": job.pk,
                "status": job.status,
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
            return JsonResponse(
                {
                    "job_id": job.pk,
                    "status": job.status,
                    "done": False,
                }
            )

        variations = []
        if job.status == AIGenerationJob.Status.SUCCEEDED:
            variations = normalize_generated_questions(job.result.get("variations") or [])

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
        topic = Topic.objects.filter(
            pk=topic_id,
            subject__program=self.course.program,
        ).select_related("subject").first()
        if not topic:
            return HttpResponse("Select a topic first.", status=400)

        choices = []
        for label in ("A", "B", "C", "D"):
            text = request.POST.get(f"choice_{label}", "").strip()
            if text:
                choices.append({"label": label, "text": text, "is_correct": label == correct_label})

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
            stem, choices, topic, difficulty, correct_label, peer_stems=peer_stems
        )

        if "application/json" in request.headers.get("Accept", ""):
            return JsonResponse(result)

        return render(
            request,
            "professor/questions/partials/validate_modal.html",
            {"result": result, "course": self.course},
        )


def _get_program_subject(course, subject_id, professor=None):
    if not subject_id or not str(subject_id).isdigit():
        return None
    subject = Subject.objects.filter(
        pk=int(subject_id),
        program=course.program,
    ).first()
    if subject and professor and not professor_can_access_subject(professor, subject):
        return None
    return subject


class TopicListView(ProfessorCourseMixin, ListView):
    model = Topic
    template_name = "professor/topics/list.html"
    context_object_name = "topics"

    def get_queryset(self):
        queryset = Topic.objects.filter(
            subject__program=self.course.program,
        ).select_related("subject")
        subject_id = self.request.GET.get("subject")
        if subject_id and subject_id.isdigit():
            queryset = queryset.filter(subject_id=int(subject_id))
        return queryset.order_by("name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "topics"
        context["year_levels"] = YearLevel.objects.all()
        context["program"] = self.course.program
        subject_id = self.request.GET.get("subject", "")
        context["selected_subject_id"] = subject_id
        selected_subject = _get_program_subject(self.course, subject_id, self.request.user)
        context["selected_subject"] = selected_subject
        return context


class TopicCreateView(ProfessorCourseMixin, View):
    def post(self, request, course_pk):
        subject = _get_program_subject(self.course, request.POST.get("subject"), request.user)
        if not subject:
            messages.error(request, "Select a valid course code first.")
            return redirect(
                reverse("analytics_professor:topic_list", kwargs={"course_pk": course_pk})
            )
        form = TopicForm(request.POST)
        if form.is_valid():
            topic = form.save(commit=False)
            topic.subject = subject
            try:
                topic.save()
                messages.success(request, f'Topic "{topic.name}" added.')
            except IntegrityError:
                messages.error(request, "A topic with this name already exists for this course.")
        else:
            messages.error(request, "Enter a valid topic name.")
        return redirect(
            reverse("analytics_professor:topic_list", kwargs={"course_pk": course_pk})
            + f"?subject={subject.pk}"
        )


class TopicUpdateView(ProfessorCourseMixin, View):
    def post(self, request, course_pk, topic_pk):
        topic = get_object_or_404(
            Topic,
            pk=topic_pk,
            subject__program=self.course.program,
        )
        form = TopicForm(request.POST, instance=topic)
        if form.is_valid():
            form.save()
            messages.success(request, "Topic updated.")
        else:
            messages.error(request, "Enter a valid topic name.")
        return redirect(
            reverse("analytics_professor:topic_list", kwargs={"course_pk": course_pk})
            + f"?subject={topic.subject_id}"
        )


class TopicDeleteView(ProfessorCourseMixin, View):
    def post(self, request, course_pk, topic_pk):
        topic = get_object_or_404(
            Topic,
            pk=topic_pk,
            subject__program=self.course.program,
        )
        subject_id = topic.subject_id
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
            + f"?subject={subject_id}"
        )

