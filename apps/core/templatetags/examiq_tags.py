from django import template

register = template.Library()

CONFIDENCE_LABELS = {
    None: "No Confidence",
    1: "Low Confidence",
    3: "Average Confidence",
    5: "High Confidence",
}

DIFFICULTY_LABELS = {
    "easy": "Beginner",
    "medium": "Intermediate",
    "hard": "Advanced",
}


@register.filter
def difficulty_label(value):
    """Map stored difficulty code to display label."""
    if value is None:
        return ""
    text = str(value).lower()
    return DIFFICULTY_LABELS.get(text, str(value))


@register.filter
def confidence_label(value):
    """Map numeric confidence (1/3/5) to display label."""
    if value is None or value == "":
        return CONFIDENCE_LABELS[None]
    try:
        return CONFIDENCE_LABELS.get(int(value), str(value))
    except (TypeError, ValueError):
        return str(value)


@register.filter
def confidence_tier_key(value):
    """Map numeric confidence to tier CSS key (none/low/average/high)."""
    from apps.analytics.confidence import confidence_tier_key as tier_key_fn

    if value is None or value == "":
        return tier_key_fn(None)
    try:
        return tier_key_fn(int(value))
    except (TypeError, ValueError):
        return "none"


@register.filter
def confidence_tier_badge(value):
    """Map tier key to display label."""
    from apps.analytics.confidence import CONFIDENCE_TIER_LABELS

    if value in CONFIDENCE_TIER_LABELS:
        return CONFIDENCE_TIER_LABELS[value]
    return str(value)
