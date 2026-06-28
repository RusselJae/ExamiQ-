from django import template

register = template.Library()

CONFIDENCE_LABELS = {1: "Low", 3: "Average", 5: "High"}

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
    try:
        return CONFIDENCE_LABELS.get(int(value), str(value))
    except (TypeError, ValueError):
        return str(value)
