from django.contrib import messages
from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView, UpdateView

from apps.analytics.confidence import confidence_accuracy_matrix
from apps.analytics.models import MistakeRecord
from apps.analytics.services import department_math_analytics, program_performance_summary
from apps.core.filtering import build_filter_fields, get_filter_param, has_active_filters
from apps.core.mixins import ChairpersonRequiredMixin, QuestionApprovalMixin
from apps.questions.forms import ExplanationStepFormSet, QuestionChoiceFormSet, QuestionForm
from apps.questions.models import Question, Topic
from apps.questions.services import approve_question, reject_question
from apps.research.models import SurveyResponse
from apps.reviews.models import Answer, ReviewSession
from apps.users.constants import PROGRAM_DEFINITIONS, home_programs_for_department, students_in_department
from apps.users.models import Course, Program, User


class ChairpersonDashboardView(ChairpersonRequiredMixin, TemplateView):
    template_name = "analytics/chairperson/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        department = self.request.user.department
        dept_slugs = set(home_programs_for_department(department)) if department else set()
        programs = Program.objects.all().order_by("name")
        if department:
            programs = programs.filter(slug__in=dept_slugs) if dept_slugs else programs.filter(
                managing_department=department
            )
        summaries = [
            program_performance_summary(program, department=department) for program in programs
        ]
        for summary in summaries:
            summary["has_activity"] = summary["total_answers"] > 0
        context["program_summaries"] = summaries
        context["dashboard_stats"] = {
            "program_count": len(summaries),
            "with_activity": sum(1 for row in summaries if row["has_activity"]),
            "total_sessions": sum(row["sessions_completed"] for row in summaries),
            "total_answers": sum(row["total_answers"] for row in summaries),
        }
        context["all_programs"] = [
            {"slug": slug, "name": name}
            for slug, name, _dept in PROGRAM_DEFINITIONS
        ]
        context["department"] = department
        return context


class QuestionReviewListView(ChairpersonRequiredMixin, ListView):
    model = Question
    template_name = "chairperson/questions/review.html"
    context_object_name = "questions"
    paginate_by = 15

    def get_queryset(self):
        department = self.request.user.department
        if not department:
            return Question.objects.none()
        queryset = (
            Question.objects.filter(
                status=Question.Status.PENDING,
                topic__subject__program__managing_department=department,
            )
            .select_related("topic", "topic__subject__program", "proposed_by")
            .order_by("created")
        )

        search = get_filter_param(self.request, "q")
        if search:
            queryset = queryset.filter(
                Q(stem__icontains=search)
                | Q(proposed_by__first_name__icontains=search)
                | Q(proposed_by__last_name__icontains=search)
                | Q(proposed_by__email__icontains=search)
            )

        program_id = get_filter_param(self.request, "program")
        if program_id.isdigit():
            queryset = queryset.filter(topic__subject__program_id=int(program_id))

        topic_id = get_filter_param(self.request, "topic")
        if topic_id.isdigit():
            queryset = queryset.filter(topic_id=int(topic_id))

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        department = self.request.user.department
        programs = Program.objects.filter(managing_department=department).order_by("name")
        topics = Topic.objects.filter(subject__program__managing_department=department).order_by(
            "subject__program__name", "name"
        )
        filter_names = ["q", "program", "topic"]
        context["filter_form_fields"] = build_filter_fields(
            self.request,
            [
                {
                    "type": "search",
                    "name": "q",
                    "label": "Search",
                    "placeholder": "Question text or proposer",
                },
                {
                    "type": "select",
                    "name": "program",
                    "label": "Program",
                    "choices": [(str(program.pk), program.name) for program in programs],
                },
                {
                    "type": "select",
                    "name": "topic",
                    "label": "Topic",
                    "choices": [
                        (str(topic.pk), f"{topic.subject.program.name} · {topic.name}")
                        for topic in topics
                    ],
                },
            ],
        )
        context["filter_has_active"] = has_active_filters(self.request, filter_names)
        return context


class QuestionReviewApproveView(QuestionApprovalMixin, View):
    def post(self, request, question_pk):
        question = get_object_or_404(
            Question,
            pk=question_pk,
            status=Question.Status.PENDING,
            topic__subject__program__managing_department=request.user.department,
        )
        approve_question(question, request.user)
        messages.success(request, "Question approved and published.")
        return redirect("analytics_chairperson:question_review")


class QuestionReviewRejectView(QuestionApprovalMixin, View):
    def post(self, request, question_pk):
        question = get_object_or_404(
            Question,
            pk=question_pk,
            status=Question.Status.PENDING,
            topic__subject__program__managing_department=request.user.department,
        )
        note = request.POST.get("rejection_note", "")
        reject_question(question, request.user, note=note)
        messages.warning(request, "Question rejected.")
        return redirect("analytics_chairperson:question_review")


class QuestionReviewEditView(QuestionApprovalMixin, UpdateView):
    model = Question
    form_class = QuestionForm
    template_name = "chairperson/questions/review_form.html"
    pk_url_kwarg = "question_pk"

    def get_queryset(self):
        return Question.objects.filter(
            status=Question.Status.PENDING,
            topic__subject__program__managing_department=self.request.user.department,
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["program"] = self.object.topic.subject.program
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["choice_formset"] = QuestionChoiceFormSet(self.request.POST, instance=self.object)
            context["step_formset"] = ExplanationStepFormSet(self.request.POST, instance=self.object)
        else:
            context["choice_formset"] = QuestionChoiceFormSet(instance=self.object)
            context["step_formset"] = ExplanationStepFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        choice_formset = context["choice_formset"]
        step_formset = context["step_formset"]
        if not (choice_formset.is_valid() and step_formset.is_valid()):
            return self.form_invalid(form)
        self.object = form.save()
        choice_formset.save()
        step_formset.save()
        approve_question(self.object, self.request.user)
        messages.success(self.request, "Question edited and approved.")
        return redirect("analytics_chairperson:question_review")


class CrossProgramAnalyticsView(ChairpersonRequiredMixin, TemplateView):
    template_name = "analytics/chairperson/by_program.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["analytics"] = department_math_analytics(self.request.user.department)
        return context


class CourseAuditView(ChairpersonRequiredMixin, ListView):
    model = Course
    template_name = "analytics/chairperson/course_audit.html"
    context_object_name = "courses"
    paginate_by = 25

    def get_queryset(self):
        department = self.request.user.department
        student_ids = students_in_department(department).values_list("pk", flat=True)
        queryset = (
            Course.objects.filter(review_sessions__student_id__in=student_ids)
            .select_related("professor", "program")
            .distinct()
            .order_by("-academic_year", "term", "code")
        )

        search = get_filter_param(self.request, "q")
        if search:
            queryset = queryset.filter(
                Q(code__icontains=search)
                | Q(name__icontains=search)
                | Q(professor__first_name__icontains=search)
                | Q(professor__last_name__icontains=search)
                | Q(professor__email__icontains=search)
            )

        program_id = get_filter_param(self.request, "program")
        if program_id.isdigit():
            queryset = queryset.filter(program_id=int(program_id))

        term = get_filter_param(self.request, "term")
        if term:
            queryset = queryset.filter(term=term)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        department = self.request.user.department
        programs = Program.objects.filter(managing_department=department).order_by("name")
        student_ids = students_in_department(department).values_list("pk", flat=True)
        terms = (
            Course.objects.filter(review_sessions__student_id__in=student_ids)
            .values_list("term", flat=True)
            .distinct()
            .order_by("term")
        )
        filter_names = ["q", "program", "term"]
        context["filter_form_fields"] = build_filter_fields(
            self.request,
            [
                {
                    "type": "search",
                    "name": "q",
                    "label": "Search",
                    "placeholder": "Course code, title, or faculty",
                },
                {
                    "type": "select",
                    "name": "program",
                    "label": "Program",
                    "choices": [(str(program.pk), program.name) for program in programs],
                },
                {
                    "type": "select",
                    "name": "term",
                    "label": "Term",
                    "choices": [(term, term) for term in terms],
                },
            ],
        )
        context["filter_has_active"] = has_active_filters(self.request, filter_names)
        return context


class ResearchDataExportView(ChairpersonRequiredMixin, View):
    """Anonymized department-scoped research CSV for thesis analysis."""

    def get(self, request):
        import csv
        import hashlib

        department = request.user.department
        if not department:
            return HttpResponse("No department assigned.", status=403)

        students = students_in_department(department).filter(role=User.Role.STUDENT)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="examiq_research_export.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "student_hash",
                "program",
                "sessions_completed",
                "total_answers",
                "accuracy_pct",
                "avg_confidence",
                "mastery_count",
                "misconception_count",
                "lucky_guess_count",
                "expected_gap_count",
                "uncertain_count",
                "mistake_records",
                "pre_calibration_awareness",
                "pre_confidence_usefulness",
                "pre_would_recommend",
                "post_calibration_awareness",
                "post_confidence_usefulness",
                "post_would_recommend",
            ]
        )

        for student in students:
            sessions = ReviewSession.objects.filter(
                student=student,
                status=ReviewSession.Status.COMPLETED,
            )
            answers = Answer.objects.filter(session__student=student)
            total = answers.count()
            correct = answers.filter(is_correct=True).count()
            accuracy = round(correct / total * 100, 1) if total else 0.0
            avg_confidence = answers.aggregate(avg=Avg("confidence"))["avg"] or 0
            matrix = confidence_accuracy_matrix(answers)
            mistakes = MistakeRecord.objects.filter(student=student).count()

            pre = SurveyResponse.objects.filter(
                student=student, survey_type=SurveyResponse.SurveyType.PRE
            ).first()
            post = SurveyResponse.objects.filter(
                student=student, survey_type=SurveyResponse.SurveyType.POST
            ).first()

            student_hash = hashlib.sha256(f"examiq-research-{student.pk}".encode()).hexdigest()[:16]
            writer.writerow(
                [
                    student_hash,
                    student.home_degree_program or "",
                    sessions.count(),
                    total,
                    accuracy,
                    round(avg_confidence, 1),
                    matrix.get("mastery", 0),
                    matrix.get("misconception", 0),
                    matrix.get("lucky_guess", 0),
                    matrix.get("expected_gap", 0),
                    matrix.get("uncertain", 0),
                    mistakes,
                    pre.calibration_awareness if pre else "",
                    pre.confidence_rating_usefulness if pre else "",
                    pre.would_recommend if pre else "",
                    post.calibration_awareness if post else "",
                    post.confidence_rating_usefulness if post else "",
                    post.would_recommend if post else "",
                ]
            )

        return response
