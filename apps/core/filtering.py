"""Shared helpers for GET-based list filtering."""

from __future__ import annotations

from typing import Any


def get_filter_param(request, name: str, default: str = "") -> str:
    """Return a stripped GET parameter value."""
    return request.GET.get(name, default).strip()


def build_filter_fields(request, specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build template-ready filter field definitions from request GET params."""
    fields: list[dict[str, Any]] = []
    for spec in specs:
        field = dict(spec)
        name = spec["name"]
        if spec["type"] == "search":
            field["value"] = get_filter_param(request, name)
        elif spec["type"] == "select":
            field["selected"] = get_filter_param(request, name)
        fields.append(field)
    return fields


def has_active_filters(request, names: list[str]) -> bool:
    """Return True when any named GET filter param has a value."""
    return any(get_filter_param(request, name) for name in names)
