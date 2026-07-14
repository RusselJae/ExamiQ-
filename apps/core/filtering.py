"""Shared helpers for GET-based list filtering."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from django.db.models import QuerySet
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone


def get_filter_param(request, name: str, default: str = "") -> str:
    """Return a stripped GET parameter value."""
    return request.GET.get(name, default).strip()


def redirect_preserving_filters(
    request,
    viewname: str,
    *args,
    **kwargs,
) -> HttpResponseRedirect:
    """Redirect to a list view, keeping filters when Referer matches that path.

    Table row POSTs must not wipe active GET filters. Filters clear only via the
    explicit Remove filters control (bare list URL).
    """
    fallback = reverse(viewname, args=args, kwargs=kwargs)
    referer = request.META.get("HTTP_REFERER", "")
    if not referer:
        return redirect(fallback)

    parsed = urlparse(referer)
    if parsed.netloc and parsed.netloc != request.get_host():
        return redirect(fallback)
    if parsed.path.rstrip("/") != fallback.rstrip("/"):
        return redirect(fallback)

    target = fallback
    if parsed.query:
        target = f"{fallback}?{parsed.query}"
    return redirect(target)


def build_filter_fields(request, specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build template-ready filter field definitions from request GET params."""
    fields: list[dict[str, Any]] = []
    for spec in specs:
        field = dict(spec)
        name = spec["name"]
        if spec["type"] == "search":
            field["value"] = get_filter_param(request, name)
        elif spec["type"] in ("select", "sort"):
            field["selected"] = get_filter_param(request, name)
        elif spec["type"] == "date":
            field["value"] = get_filter_param(request, name)
        fields.append(field)
    return fields


def has_active_filters(request, names: list[str]) -> bool:
    """Return True when any named GET filter param has a value."""
    return any(get_filter_param(request, name) for name in names)


def apply_date_range(qs: QuerySet, request, field_name: str) -> QuerySet:
    """Filter queryset by optional date_from / date_to (YYYY-MM-DD) on a datetime field."""
    date_from = get_filter_param(request, "date_from")
    date_to = get_filter_param(request, "date_to")
    if date_from:
        try:
            start = timezone.make_aware(datetime.strptime(date_from, "%Y-%m-%d"))
            qs = qs.filter(**{f"{field_name}__gte": start})
        except ValueError:
            pass
    if date_to:
        try:
            end = timezone.make_aware(datetime.strptime(date_to, "%Y-%m-%d")).replace(
                hour=23, minute=59, second=59
            )
            qs = qs.filter(**{f"{field_name}__lte": end})
        except ValueError:
            pass
    return qs


def apply_sort(
    qs: QuerySet,
    request,
    *,
    newest_field: str,
    oldest_field: str | None = None,
    default: str = "newest",
) -> QuerySet:
    """Apply sort=newest|oldest to queryset."""
    sort = get_filter_param(request, "sort", default)
    if sort == "oldest" and oldest_field:
        return qs.order_by(oldest_field)
    return qs.order_by(newest_field)


STANDARD_DATE_SORT_FILTER_SPECS = [
    {
        "type": "date",
        "name": "date_from",
        "label": "From",
    },
    {
        "type": "date",
        "name": "date_to",
        "label": "To",
    },
    {
        "type": "sort",
        "name": "sort",
        "label": "Order",
        "choices": [
            ("newest", "Newest first"),
            ("oldest", "Oldest first"),
        ],
    },
]
