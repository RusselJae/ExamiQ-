from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
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


class ChairpersonRequiredMixin(RoleRequiredMixin):
    required_role = User.Role.CHAIRPERSON


class CampusAdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Require Django superuser for in-app campus administration."""

    def test_func(self) -> bool:
        return self.request.user.is_authenticated and self.request.user.is_superuser


class ProfessorCourseMixin(ProfessorRequiredMixin):
    """Ensure the professor owns the course referenced in the URL."""

    course: Course | None = None

    def get_course_pk(self) -> int:
        return self.kwargs.get("course_pk") or self.kwargs["pk"]

    def dispatch(self, request, *args, **kwargs):
        self.course = get_object_or_404(
            Course,
            pk=self.get_course_pk(),
            professor=request.user,
        )
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
