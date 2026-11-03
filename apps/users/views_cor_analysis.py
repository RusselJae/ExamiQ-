"""Anonymous COR analysis endpoint used by the signup page.

Accepts one POSTed file, runs deterministic extraction + LLM structuring +
catalog matching, and returns the matched subjects with their faculty
options. Nothing persists — the student reviews and picks before the signup
form itself is submitted (the COR file rides along in that POST).
"""

from django.http import JsonResponse
from django.urls import reverse
from django.views import View

from apps.core.audit import log_audit_event
from apps.users.cor_services import (
    ALLOWED_EXTENSIONS,
    CorAnalysisError,
    analyze_cor_upload,
)


class CorAnalyzeView(View):
    """AJAX: uploaded COR file → detected subjects + faculty options."""

    http_method_names = ["post"]

    def post(self, request):
        uploaded = request.FILES.get("cor_file")
        if not uploaded:
            return JsonResponse({"error": "Attach your COR file first."}, status=400)
        name = (uploaded.name or "").lower()
        if not name.endswith(ALLOWED_EXTENSIONS):
            return JsonResponse(
                {"error": "Upload the COR as a PDF, PNG, JPG, or WebP."}, status=400
            )
        if uploaded.size > 8 * 1024 * 1024:
            return JsonResponse(
                {"error": "That file is larger than 8 MB. Compress it first."},
                status=400,
            )

        try:
            result = analyze_cor_upload(uploaded)
        except CorAnalysisError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except Exception:  # noqa: BLE001 - never 500 the signup page
            log_audit_event(
                request.user,
                action="cor_analyze_error",
                metadata={"filename": name},
            )
            return JsonResponse(
                {
                    "error": "The analyzer hit a snag. Pick your subjects "
                    "manually below — nothing was lost."
                },
                status=503,
            )

        from apps.users.cor_services import store_cor_verification
        from apps.users.services import subject_faculty_options

        subject_ids = [m["subject_id"] for m in result["matched"]]
        faculty_by_subject = subject_faculty_options(subject_ids) if subject_ids else {}
        for subject in result["matched"]:
            subject["faculty"] = [
                {
                    "faculty_pk": f["faculty_pk"],
                    "faculty_name": f["name"],
                    "section_label": f["section_label"],
                    "enrolled": f["enrolled"],
                    "capacity": f["capacity"],
                }
                for f in faculty_by_subject.get(subject["subject_id"], [])
            ]

        store_cor_verification(request, uploaded, result)

        return JsonResponse(
            {
                "ok": True,
                "matched": result["matched"],
                "unmatched": result["unmatched"],
                "rows": result["rows"],
                "cor_type": result["cor_type"],
                "suggested_year_level": result["suggested_year_level"],
                "review_url": "",
                "faculty_list_url": "",
                "signup_url": reverse("account_signup"),
            }
        )
