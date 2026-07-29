import pytest
from django.core.exceptions import ValidationError

from apps.users.section_services import parse_section_label


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1M", "1M"),
        ("2m", "2M"),
        ("2-1M", "1M"),
        ("BSE 2-1M", "1M"),
        ("bse 1-2M", "2M"),
        ("3M", "3M"),
    ],
)
def test_parse_section_label(raw, expected):
    assert parse_section_label(raw) == expected


def test_parse_section_label_rejects_empty():
    with pytest.raises(ValidationError):
        parse_section_label("   ")
