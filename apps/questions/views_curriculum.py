"""Shared curriculum cascade API views."""

from django.http import JsonResponse
from django.views import View

from apps.questions.curriculum import (
    get_subjects_for_program,
    get_subjects_for_professor,
    get_topics_for_subject,
    get_year_levels,
)


class CurriculumSubjectsView(View):
    """GET ?program=&year_level= -> subjects JSON."""

    def get(self, request):
        program_id = request.GET.get("program")
        year_level_id = request.GET.get("year_level")
        if not program_id or not program_id.isdigit():
            return JsonResponse({"subjects": []})
        year_id = int(year_level_id) if year_level_id and year_level_id.isdigit() else None
        subjects = get_subjects_for_program(int(program_id), year_id)
        return JsonResponse({
            "subjects": [
                {"id": s.pk, "code": s.code, "name": s.name, "label": str(s)}
                for s in subjects
            ]
        })


class ProfessorCurriculumSubjectsView(CurriculumSubjectsView):
    """Professor subjects: year filter with CS catalog fallback."""

    def get(self, request, program_slug=None):
        program_id = request.GET.get("program")
        year_level_id = request.GET.get("year_level")
        if not program_id or not program_id.isdigit():
            return JsonResponse({"subjects": [], "fallback_message": ""})
        year_id = int(year_level_id) if year_level_id and year_level_id.isdigit() else None
        program_id = int(program_id)

        if program_slug == "cs":
            strict_subjects = get_subjects_for_program(program_id, year_id, strict_year=True)
            if year_id and strict_subjects.exists():
                subjects = strict_subjects
                fallback_message = ""
            else:
                subjects = get_subjects_for_professor(program_id, year_id)
                fallback_message = (
                    "No subjects for this year. Showing all CS subjects."
                    if year_id
                    else ""
                )
        else:
            subjects = get_subjects_for_program(program_id, year_id)
            fallback_message = ""

        return JsonResponse({
            "subjects": [
                {"id": s.pk, "code": s.code, "name": s.name, "label": str(s)}
                for s in subjects
            ],
            "fallback_message": fallback_message,
        })


class CurriculumTopicsView(View):
    """GET ?subject= -> topics JSON."""

    def get(self, request):
        subject_id = request.GET.get("subject")
        if not subject_id or not subject_id.isdigit():
            return JsonResponse({"topics": []})
        topics = get_topics_for_subject(int(subject_id))
        return JsonResponse({
            "topics": [{"id": t.pk, "name": t.name} for t in topics]
        })


class CurriculumYearLevelsView(View):
    """GET -> year levels JSON."""

    def get(self, request):
        levels = get_year_levels()
        return JsonResponse({
            "year_levels": [{"id": yl.pk, "order": yl.order, "name": yl.name} for yl in levels]
        })
