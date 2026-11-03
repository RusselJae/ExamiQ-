import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django

django.setup()

from django.test import Client, override_settings
from django.urls import reverse
from apps.users.assignment_services import get_or_create_catalog_course
from apps.questions.models import Subject
from apps.users.models import User

professor = User.objects.filter(role="professor").first()
subject = Subject.objects.first()
course = get_or_create_catalog_course(professor, subject)

client = Client()
client.force_login(professor)

INCLUDE_TAG = "{% include"

with override_settings(ALLOWED_HOSTS=["*"]):
    # 1. Questions list page
    response = client.get(
        reverse("analytics_professor:question_list", kwargs={"course_pk": course.pk})
    )
    content = response.content.decode()
    print("=== QUESTIONS LIST ===")
    print("Status:", response.status_code)
    print("  question-modal-add in DOM:", "question-modal-add" in content)
    print("  question-modal-edit in DOM:", "question-modal-edit" in content)
    print("  include tag literal:", INCLUDE_TAG in content)
    print("  question-modal.js loaded:", "question-modal.js" in content)
    print("  data-question-modal buttons:", content.count("data-question-modal"))

    # 2. Materials list page
    response = client.get(
        reverse("analytics_professor:material_list", kwargs={"course_pk": course.pk})
    )
    content = response.content.decode()
    print("\n=== MATERIALS LIST ===")
    print("Status:", response.status_code)
    print("  content-modal-add in DOM:", "content-modal-add" in content)
    print("  content-modal-edit in DOM:", "content-modal-edit" in content)
    print("  include tag literal:", INCLUDE_TAG in content)
    print("  content-modal.js loaded:", "content-modal.js" in content)
    print("  data-content-modal buttons:", content.count("data-content-modal"))

    # 3. Materials hub page
    response = client.get(
        reverse("analytics_professor:materials_hub") + f"?subject={subject.pk}"
    )
    content = response.content.decode()
    print("\n=== MATERIALS HUB (with subject) ===")
    print("Status:", response.status_code)
    print("  content-modal-add in DOM:", "content-modal-add" in content)
    print("  content-modal-edit in DOM:", "content-modal-edit" in content)
    print("  include tag literal:", INCLUDE_TAG in content)
    print("  content-modal.js loaded:", "content-modal.js" in content)
