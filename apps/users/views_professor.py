"""Professor course offering management views."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, ListView

from apps.core.mixins import ProfessorCourseMixin, ProfessorRequiredMixin
from apps.reviews.models import ReviewWindow
from apps.users.forms import CourseOfferingForm
from apps.users.models import Course


class ProfessorCourseListView(ProfessorRequiredMixin, ListView):
    """List active course offerings owned by the professor."""

    model = Course
    template_name = "professor/courses/list.html"
    context_object_name = "courses"

    def get_queryset(self):
        return (
            Course.objects.filter(professor=self.request.user, is_archived=False)
            .select_related("program")
            .order_by("-academic_year", "term", "code")
        )


class ProfessorCourseCreateView(ProfessorRequiredMixin, CreateView):
    model = Course
    form_class = CourseOfferingForm
    template_name = "professor/courses/form.html"

    def form_valid(self, form):
        form.instance.professor = self.request.user
        messages.success(self.request, "Course offering created.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("analytics_professor:course_list")


class ProfessorCourseCloneView(ProfessorRequiredMixin, View):
    """Clone a past offering's metadata and review-window templates into a new term."""

    def post(self, request, pk):
        source = get_object_or_404(Course, pk=pk, professor=request.user)
        new_course = Course.objects.create(
            code=source.code,
            name=source.name,
            program=source.program,
            term=request.POST.get("term", source.term),
            academic_year=request.POST.get("academic_year", source.academic_year),
            section=request.POST.get("section", "A"),
            professor=request.user,
        )
        for window in source.review_windows.all():
            topics = list(window.topics.all())
            new_window = ReviewWindow.objects.create(
                course=new_course,
                created_by=request.user,
                title=window.title,
                exam_type=window.exam_type,
                opens_at=window.opens_at,
                closes_at=window.closes_at,
                allowed_difficulties=window.allowed_difficulties,
                duration_minutes=window.duration_minutes,
                is_active=False,
            )
            new_window.topics.set(topics)
        messages.success(request, f"Cloned {source.code} into {new_course.term} {new_course.academic_year}.")
        return redirect("analytics_professor:course_list")


class ProfessorCourseArchiveView(ProfessorRequiredMixin, View):
    def post(self, request, pk):
        course = get_object_or_404(Course, pk=pk, professor=request.user)
        course.is_archived = True
        course.save(update_fields=["is_archived"])
        messages.success(request, f"{course.code} archived.")
        return redirect("analytics_professor:course_list")
