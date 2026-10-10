"""Shared validation for person name fields."""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError

# Letters (incl. common accented Latin), spaces, hyphens, and apostrophes.
NAME_PATTERN = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ]+(?:[ '\-][A-Za-zÀ-ÖØ-öø-ÿ]+)*$")
NAME_MAX_LENGTH = 100


def clean_person_name(value: str, *, field_label: str = "Name", required: bool = True) -> str:
    """Normalize and validate a person name; raise ValidationError on failure."""
    cleaned = (value or "").strip()
    if not cleaned:
        if required:
            raise ValidationError(f"{field_label} is required.")
        return ""
    if len(cleaned) > NAME_MAX_LENGTH:
        raise ValidationError(
            f"{field_label} must be at most {NAME_MAX_LENGTH} characters."
        )
    if not NAME_PATTERN.fullmatch(cleaned):
        raise ValidationError(
            f"{field_label} may only contain letters, spaces, hyphens, and apostrophes."
        )
    return cleaned
