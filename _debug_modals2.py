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

with override_settings(ALLOWED_HOSTS=["*"]):
    response = client.get(
        reverse("analytics_professor:question_list", kwargs={"course_pk": course.pk})
    )
    content = response.content.decode()

    # Find all literal include tags
    idx = 0
    while True:
        idx = content.find("{% include", idx)
        if idx < 0:
            break
        print(f"--- literal include at {idx} ---")
        print(repr(content[idx : idx + 200]))
        print()
        idx += 10
