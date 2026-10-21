"""Report the ONLYOFFICE Document Server setup and the DOCX toolchain.

Run this on the deployed host (e.g. Railway) to see exactly why the editor
is not rendering a .docx:

    python manage.py check_office
"""

from __future__ import annotations

import importlib.util

from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import reverse

from apps.ai.office_editor import (
    is_configured,
    public_base_url,
    railway_public_base_url,
    server_url,
)


class Command(BaseCommand):
    help = "Diagnose the ONLYOFFICE Document Server integration."

    def add_header(self, text: str) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING(text))

    def add_ok(self, text: str) -> None:
        self.stdout.write(self.style.SUCCESS(f"  OK    {text}"))

    def add_warn(self, text: str) -> None:
        self.stdout.write(self.style.WARNING(f"  WARN  {text}"))

    def add_bad(self, text: str) -> None:
        self.stdout.write(self.style.ERROR(f"  FAIL  {text}"))

    def handle(self, *args, **options) -> None:
        self.add_header("Document Server")
        if is_configured():
            self.add_ok(f"ONLYOFFICE_DOCUMENT_SERVER_URL = {server_url()}")
        else:
            self.add_bad(
                "ONLYOFFICE_DOCUMENT_SERVER_URL is not set - the built-in HTML "
                "editor is used instead of ONLYOFFICE."
            )

        jwt_secret = getattr(settings, "ONLYOFFICE_JWT_SECRET", "") or ""
        if jwt_secret:
            self.add_ok("ONLYOFFICE_JWT_SECRET is set")
        else:
            self.add_bad(
                "ONLYOFFICE_JWT_SECRET is empty - the Document Server will "
                "reject every token."
            )

        self.add_header("Public origin (used by the Document Server)")
        railway = railway_public_base_url()
        configured = (getattr(settings, "ONLYOFFICE_PUBLIC_BASE_URL", "") or "").strip()
        effective = public_base_url()
        if effective:
            self.add_ok(f"effective public base URL = {effective}")
        else:
            self.add_warn(
                "No public base URL - the Document Server will use the request "
                "host, which is unreachable from outside."
            )
        if railway:
            self.add_ok(f"Railway public domain = {railway}")
        if configured and effective and configured.rstrip("/") != effective:
            self.add_warn(
                f"ONLYOFFICE_PUBLIC_BASE_URL ({configured}) is being ignored "
                f"in favour of {effective}."
            )

        self.add_header("DOCX toolchain")
        for module, label in (
            ("docx", "python-docx (HTML -> DOCX export)"),
            ("mammoth", "mammoth (DOCX -> HTML import)"),
            ("PIL", "Pillow (image handling)"),
        ):
            if importlib.util.find_spec(module) is None:
                self.add_bad(f"{label} is NOT installed")
            else:
                self.add_ok(f"{label} is installed")

        self.add_header("Callback URL")
        try:
            callback = reverse(
                "analytics_professor:material_office_callback",
                kwargs={"course_pk": 0, "pk": 0},
            )
        except Exception:  # noqa: BLE001 - URL config may not be loaded
            callback = "(unavailable)"
        self.add_ok(f"POST {callback}")
        self.stdout.write(
            "  The Document Server must be able to POST to this URL; the "
            "callback is JWT-authenticated and CSRF-exempt."
        )
