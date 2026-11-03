"""Template helpers for shared list filter bars."""

from __future__ import annotations

from django import template

from apps.core.filtering import count_advanced_active_filters

register = template.Library()


@register.simple_tag
def active_advanced_filter_count(fields) -> int:
    """Return how many non-search filters currently have a value."""
    return count_advanced_active_filters(fields or [])


@register.simple_tag
def advanced_filter_field_count(fields) -> int:
    """Return how many non-search filter fields exist (regardless of value)."""
    fields = fields or []
    return sum(1 for field in fields if field.get("type") != "search")


@register.simple_tag
def active_filter_count(fields) -> int:
    """Return how many filter fields (any type) currently have a value."""
    fields = fields or []
    return sum(1 for field in fields if field.get("active_display"))
