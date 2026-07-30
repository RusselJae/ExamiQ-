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
)
from apps.users.assignment_services import (
    get_assigned_subjects_queryset,
    get_professor_course_queryset,
    professor_can_access_subject,
)
from apps.users.models import Course
from apps.questions.validation import validate_question_for_submit





class QuestionListView(ProfessorCourseMixin, ListView):

    model = Question

    template_name = "professor/questions/list.html"

    context_object_name = "questions"

    paginate_by = 25



    def get_queryset(self):

        course_subject = _subject_for_course(self.course)
        queryset = Question.objects.select_related("topic", "topic__subject").annotate(
            mistake_count=Count("mistake_records")
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
        topics = topics_for_course_section(self.course, self.request.user)
        subject = _subject_for_course(self.course)
        return {
            "course": self.course,
            "active_tab": "questions",
            "form_title": "Add Questions",
            "topics": topics,
            "course_subject": subject,
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
        topic = topics_for_course_section(self.course, request.user).filter(
            pk=topic_id
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
            question_type = Question.QuestionType.MCQ
            skip_ai_gate = request.POST.get(f"ai_generated_{index}", "") == "1"
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
                stem,
                choices_data,
                topic,
                difficulty,
                correct_label,
                ai_enabled=False,
                question_type=question_type,
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
            question_payload = {
                "topic": topic,
                "difficulty": difficulty,
                "question_type": question_type,
                "stem": stem,
                "concept_tag": concept_tag,
                "is_active": True,
                "status": Question.Status.APPROVED,
                "proposed_by": request.user,
            }

            question = create_question(
                question_payload,
                choices_data,
                steps,
            )
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
            messages.success(request, f"Saved {created} question(s) to the question bank.")
            return redirect("analytics_professor:question_list", course_pk=self.course.pk)
        if not skipped_invalid and not skipped_duplicates:
            messages.warning(request, "No questions were saved. Add at least one complete question.")
        return render(request, self.template_name, self.get_context_data())


class QuestionAIGenerateView(ProfessorCourseMixin, View):
    """Enqueue AI question generation and return a job id for polling."""

    def post(self, request, course_pk):
        from apps.ai.ingest import ingest_learning_upload
        from apps.ai.job_services import start_question_generation_job
        from apps.ai.retrieval import retrieve_material_for_topic, sample_material_for_detection
        from apps.ai.source_extract import SourceMaterialError
        from apps.ai.subject_relevance import assess_subject_relevance

        difficulty = request.POST.get("difficulty", Question.Difficulty.EASY)
        try:
            count = int(request.POST.get("count") or 3)
        except (TypeError, ValueError):
            count = 3
        count = max(1, min(count, 10))

        subject = _subject_for_course(self.course)
        if not subject:
            return JsonResponse(
                {"error": "Link a subject to this course before generating."},
                status=400,
            )
        topics = list(
            topics_for_course_section(self.course, request.user).select_related("subject")
        )
        if not topics:
            return JsonResponse(
                {"error": "Create at least one topic under this course subject first."},
                status=400,
            )

        uploaded = request.FILES.get("source_file")
        if not uploaded:
            return JsonResponse(
                {"error": "Upload a module or learning material file to generate questions."},
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

        sample = sample_material_for_detection(document)
        relevance = assess_subject_relevance(sample, subject, topics)
        if not relevance["related"]:
            return JsonResponse(
                {
                    "error": relevance.get("reason")
                    or "Uploaded module is not related to this course subject.",
                },
                status=400,
            )

        topic_id = relevance.get("matched_topic_id") or request.POST.get("topic")
        try:
            topic_id = int(topic_id) if topic_id is not None else None
        except (TypeError, ValueError):
            topic_id = None
        topic = next((t for t in topics if t.pk == topic_id), None) if topic_id else None
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
        topic = (
            topics_for_course_section(self.course, request.user)
            .filter(pk=topic_id)
            .select_related("subject")
            .first()
        )
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
            stem,
            choices,
            topic,
            difficulty,
            correct_label,
            peer_stems=peer_stems,
            question_type=Question.QuestionType.MCQ,
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
    if subject and professor and not professor_can_access_subject(professor, subject):
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
    if professor is not None and not professor_can_access_subject(professor, subject):
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
                reverse("analytics_professor:topic_list", kwargs={"course_pk": course_pk})
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
                        {"error": "A topic with this name already exists for this course."},
                        status=400,
                    )
                messages.error(request, "A topic with this name already exists for this course.")
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

