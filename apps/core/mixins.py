from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404
from django.shortcuts import get_object_or_404

from apps.users.models import Course, Program, User


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Base mixin requiring a specific user role."""

    required_role: str = ""

    def test_func(self) -> bool:
        return self.request.user.is_authenticated and self.request.user.role == self.required_role


class StudentRequiredMixin(RoleRequiredMixin):
    required_role = User.Role.STUDENT


class ProfessorRequiredMixin(RoleRequiredMixin):
    required_role = User.Role.PROFESSOR


class FacultyLegacyRosterBlockedMixin:
    """Raise 404 for retired section/masterlist analytics screens."""

    def dispatch(self, request, *args, **kwargs):
        raise Http404()


class ChairpersonRequiredMixin(RoleRequiredMixin):
    required_role = User.Role.CHAIRPERSON


class CampusAdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Require campus administrator role or Django superuser."""

    def test_func(self) -> bool:
        user = self.request.user
        return user.is_authenticated and (
            user.is_superuser or user.role == User.Role.CAMPUS_ADMIN
        )


class ProfessorCourseMixin(ProfessorRequiredMixin):
    """Ensure the professor owns the course referenced in the URL."""

    course: Course | None = None

    def get_course_pk(self) -> int:
        return self.kwargs.get("course_pk") or self.kwargs["pk"]

    def dispatch(self, request, *args, **kwargs):
        from apps.users.assignment_services import professor_can_access_course

        course = get_object_or_404(Course, pk=self.get_course_pk())
        if not professor_can_access_course(request.user, course):
            raise Http404()
        self.course = course
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["course"] = self.course
        return context


class ChairpersonProgramMixin(ChairpersonRequiredMixin):
    """Ensure the program is manageable by the chairperson's department."""

    program: Program | None = None

    def dispatch(self, request, *args, **kwargs):
        self.program = get_object_or_404(
            Program,
            pk=self.kwargs["program_pk"],
            managing_department=request.user.department,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["program"] = self.program
        return context


class QuestionApprovalMixin(ChairpersonRequiredMixin):
    """Chairperson can act on questions for programs their department manages."""

    def can_approve_questions(self) -> bool:
        user = self.request.user
        if not user.department_id:
            return False
        from apps.questions.models import Question

        question_pk = self.kwargs.get("question_pk")
        if question_pk:
            return Question.objects.filter(
                pk=question_pk,
                topic__subject__program__managing_department_id=user.department_id,
            ).exists()
        return Program.objects.filter(managing_department_id=user.department_id).exists()

    def test_func(self) -> bool:
        return super().test_func() and self.can_approve_questions()
