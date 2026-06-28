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

from apps.core.filtering import build_filter_fields, get_filter_param, has_active_filters
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
    build_steps_from_post,
    create_question,
    deactivate_question,
    find_duplicate_question,
    submit_question_for_review,
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

            .select_related("topic")

            .annotate(mistake_count=Count("mistake_records"))

            .order_by("topic__name", "difficulty", "status")

        )

        search = get_filter_param(self.request, "q")
        if search:
            queryset = queryset.filter(stem__icontains=search)

        topic_id = get_filter_param(self.request, "topic")
        if topic_id.isdigit():
            queryset = queryset.filter(topic_id=int(topic_id))

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
        filter_names = ["q", "topic", "difficulty", "type", "active"]
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

        self.object.status = Question.Status.PENDING

        self.object.proposed_by = self.request.user

        self.object.save()

        choice_formset.instance = self.object

        choice_formset.save()

        messages.success(self.request, "Question submitted for chairperson review.")

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

        submit_question_for_review(self.object, self.request.user)

        messages.success(self.request, "Changes submitted for chairperson review.")

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





class QuestionGenerateVariationsView(ProfessorCourseMixin, View):

    def post(self, request, course_pk, question_pk):

        question = Question.objects.filter(

            pk=question_pk,

            topic__subject__program=self.course.program,

        ).select_related("topic").first()

        if not question:
            return HttpResponse(status=404)

        ai_error = None
        variations = []
        try:
            variations = normalize_generated_questions(
                get_question_generator().generate(
                    question.topic,
                    question.difficulty,
                    count=3,
                    reference_stem=question.stem,
                )
            )
        except AIServiceUnavailableError as exc:
            ai_error = exc.message

        return render(
            request,
            "professor/questions/partials/variations_modal.html",
            {
                "variations": variations,
                "question": question,
                "course": self.course,
                "ai_error": ai_error,
            },
        )





class QuestionConfirmVariationsView(ProfessorCourseMixin, View):

    def post(self, request, course_pk, question_pk):

        question = Question.objects.filter(

            pk=question_pk,

            topic__subject__program=self.course.program,

        ).select_related("topic").first()

        if not question:

            return HttpResponse(status=404)



        indices = request.POST.getlist("selected")

        created = 0
        skipped_invalid = 0
        skipped_duplicates: list[str] = []

        for index in indices:
            stem = request.POST.get(f"stem_{index}", "").strip()
            if not stem:
                continue
            choices_data = []
            correct_label = ""
            for label in ("A", "B", "C", "D"):
                text = request.POST.get(f"choice_{index}_{label}", "").strip()
                is_correct = request.POST.get(f"correct_{index}_{label}") == "on"
                if is_correct:
                    correct_label = label
                if text:
                    choices_data.append({"label": label, "text": text, "is_correct": is_correct})

            validation = validate_question_for_submit(
                stem, choices_data, question.topic, question.difficulty, correct_label
            )
            if not validation.get("is_valid"):
                skipped_invalid += 1
                continue

            if find_duplicate_question(question.topic_id, stem):
                skipped_duplicates.append(stem[:60])
                continue

            steps = build_steps_from_post(
                request.POST.get(f"steps_{index}", ""),
                solution_summary=request.POST.get(f"solution_summary_{index}", ""),
            )
            if not steps:
                steps = [{"order": 1, "content": f"See original question #{question.pk} for explanation pattern."}]

            create_question(
                {
                    "topic": question.topic,
                    "difficulty": question.difficulty,
                    "question_type": Question.QuestionType.MCQ,
                    "stem": stem,
                    "is_active": True,
                    "status": Question.Status.PENDING,
                    "proposed_by": request.user,
                },
                choices_data,
                steps,
            )
            created += 1

        if skipped_invalid:
            messages.error(request, f"Skipped {skipped_invalid} invalid variation(s).")
        if skipped_duplicates:
            messages.warning(
                request,
                "Skipped duplicate variation(s) already in the question bank.",
            )
        if created:
            messages.success(request, f"Created {created} variation(s) pending review.")
        else:
            messages.warning(request, "No variations were saved.")
        return redirect("analytics_professor:question_list", course_pk=self.course.pk)


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
            create_question(
                {
                    "topic": topic,
                    "difficulty": difficulty,
                    "question_type": Question.QuestionType.MCQ,
                    "stem": stem,
                    "concept_tag": concept_tag,
                    "is_active": True,
                    "status": Question.Status.PENDING,
                    "proposed_by": request.user,
                },
                choices_data,
                steps,
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
            messages.success(request, f"Submitted {created} question(s) for chairperson review.")
            return redirect("analytics_professor:question_list", course_pk=self.course.pk)
        if not skipped_invalid and not skipped_duplicates:
            messages.warning(request, "No questions were saved. Add at least one complete question.")
        return render(request, self.template_name, self.get_context_data())


class QuestionAIGenerateView(ProfessorCourseMixin, View):
    def post(self, request, course_pk):
        topic_id = request.POST.get("topic")
        difficulty = request.POST.get("difficulty", Question.Difficulty.EASY)
        topic = Topic.objects.filter(
            pk=topic_id,
            subject__program=self.course.program,
        ).select_related("subject").first()
        if not topic:
            return HttpResponse("Select a topic first.", status=400)

        ai_error = None
        variations = []
        try:
            variations = normalize_generated_questions(
                get_question_generator().generate(topic, difficulty, count=3)
            )
        except AIServiceUnavailableError as exc:
            ai_error = exc.message

        return render(
            request,
            "professor/questions/partials/generate_modal.html",
            {
                "variations": variations,
                "course": self.course,
                "topic": topic,
                "difficulty": difficulty,
                "ai_error": ai_error,
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

