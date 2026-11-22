"""Landing page copy should use the full degree program name."""

import pytest
from django.urls import reverse

FULL_PROGRAM_NAME = "Bachelor of Secondary Education major in Mathematics"


@pytest.mark.django_db
def test_landing_page_uses_full_degree_name(client):
    content = client.get(reverse("core:home")).content.decode()

    assert FULL_PROGRAM_NAME in content
    assert "BSEd" not in content
