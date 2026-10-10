"""Template helpers for shared list filter bars."""

from __future__ import annotations

from django import template

from apps.core.filtering import count_advanced_active_filters

register = template.Library()


@register.simple_tag
def active_advanced_filter_count(fields) -> int:
    """Return how many non-search filters currently have a value."""
    return count_advanced_active_filters(fields or [])
