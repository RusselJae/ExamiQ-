import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django

django.setup()

from django.template import Context, Template

# Test 1: single-line include
t1 = Template(
    'A {% include "components/difficulty_pill.html" with difficulty="easy" %} B'
)
r1 = t1.render(Context({}))
print("Single-line include works:", "{% include" not in r1, "| output:", repr(r1[:120]))

# Test 2: multi-line include
t2 = Template(
    'A {% include "components/difficulty_pill.html" with\n difficulty="easy" %} B'
)
r2 = t2.render(Context({}))
print("Multi-line include works:", "{% include" not in r2, "| output:", repr(r2[:120]))
