"""JSON API for program section lookup."""

from django.http import JsonResponse
from django.views import View

from apps.users.models import Program
from apps.users.section_services import get_current_academic_year, sections_for_student


class ProgramSectionsAPIView(View):
    """GET ?program=cs&year_level=1 — active sections with remaining slots."""

    def get(self, request):
        program_slug = request.GET.get("program", "").strip()
        year_level_id = request.GET.get("year_level", "")
        academic_year_label = request.GET.get("academic_year", "").strip()

        if not program_slug or not year_level_id.isdigit():
            return JsonResponse({"sections": [], "academic_year": ""})

        academic_year = get_current_academic_year()
        if academic_year_label:
            from apps.users.models import AcademicYear

            academic_year = AcademicYear.objects.filter(label=academic_year_label).first()

        sections = sections_for_student(program_slug, int(year_level_id), academic_year=academic_year)
        current_label = academic_year.label if academic_year else ""

        return JsonResponse({
            "academic_year": current_label,
            "sections": [
                {
                    "id": section.pk,
                    "label": section.label,
                    "display": section.display_label,
                    "remaining_slots": section.remaining_slots,
                    "is_full": section.is_full,
                }
                for section in sections
            ],
        })
