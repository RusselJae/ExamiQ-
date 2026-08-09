# ExamiQ — Agent Rules & Conventions

Self-regulated mathematics exam review system (Django 5, Python 3.12).
These rules adapt `.cursor/rules/django.mdc` to this codebase. Read them
before changing any code, and use `docs/` (system-flow, user-roles-and-workflows)
for domain context.

## General principles

- Favor clarity over cleverness — code is read more than written.
- Follow Django's "batteries included" philosophy; don't reinvent what Django provides.
- Keep views thin, models fat (but not obese). Business logic lives in
  `services.py`, never in views, urls, templates, or admin.
- Do NOT guess variable names, model fields, or import paths. Search the
  codebase first and reuse what exists. Ask for context when unsure.
- When debugging, think step by step and read each relevant file before
  choosing the most likely fix. If a fix has failed before, do not suggest
  it again — try something new.
- Don't be afraid to rewrite code, but verify behavior before and after each
  change so no existing functionality is lost.
- Every POST form/request carries CSRF protection; validate all input through forms.

## Architecture

- Settings live in `config/settings/{base,local,production}.py`, loaded via
  django-environ from `.env`. Never hardcode secrets. Add new env vars to
  `.env` with a default in `base.py`.
- Custom user model: `apps.users.models.User` (`AUTH_USER_MODEL`). Roles:
  Student, Professor, Chairperson, Campus Admin. Always scope queries by role
  and `department` / `home_degree_program` — never expose another role's data.
- Django apps live in `apps/<name>/`, each single-responsibility:
  - `core` — base models, mixins, context processors
  - `users` — accounts, roles, sections, assignments, notifications, signup approval
  - `questions` — question bank, subjects, topics, curriculum, chairperson review
  - `reviews` — review sessions, exam setup, recommendations, AI tutor
  - `analytics` — dashboards, heatmaps, insights, course/student detail
  - `ai` — LLM providers (ollama/gemini/openai), prompts, retrieval, OCR
  - `research` — research/export tooling
- Business logic goes in `<app>/services.py` as plain functions. Split large
  apps into focused modules: `exam_setup_services.py`, `assignment_services.py`,
  `notification_services.py`, `tutor_services.py`, etc.
- Use absolute imports: `from apps.<name>...` — never relative imports.
- Keep per-role code in separate files (`views_professor.py`, `urls_professor.py`,
  `views_campus.py`, `views_chairperson.py`).

## Models

- Every model needs `__str__`, `class Meta` (verbose names + meaningful
  `ordering`), and `related_name` on all FK/M2M fields.
- Add `get_absolute_url()` for models with detail pages.
- Avoid `null=True` on `CharField`/`TextField` — use `blank=True` with an
  empty-string default. Reserve `null=True` for non-string fields where NULL
  is semantically meaningful.
- Enforce invariants with database constraints (`UniqueConstraint`,
  `CheckConstraint`) rather than unenforced app-level checks.
- Use `select_related` / `prefetch_related` in views and services — never in
  model methods. Watch for N+1 queries, especially in analytics.
- Prefer model_utils `TimeStampedModel` for created/updated timestamps.
- No side effects in `save()` — use signals or service functions.
- After changing a model, create the migration with
  `python manage.py makemigrations`, review the diff, and run
  `python manage.py migrate`. Never edit a migration that has been applied
  elsewhere — create a new one.

## Views

- Keep views thin: fetch + delegate to services + render a template.
- Class-based views (`django.views.View` + `LoginRequiredMixin`) are the norm
  here. Use `PermissionRequiredMixin` or explicit role checks for
  chairperson/campus-admin-only actions.
- Use `get_object_or_404` instead of `Model.objects.get()`.
- Return meaningful HTTP status codes (404, 403, ...).
- Never query the database in templates — pass everything via context.

## Forms

- Use `ModelForm` for model-backed forms; list `fields` explicitly (never `__all__`).
- Field-level validation in `clean_<field>()`, cross-field in `clean()`.
- Render with crispy-forms (Tailwind pack). Reuse `templates/components/`
  form fields where applicable.

## URLs & Templates

- Set `app_name` in every app `urls.py`; always reference `{% url 'app:name' %}`,
  never hardcode paths.
- Templates extend `templates/base.html` (or `account/auth_base.html`,
  `landing/base.html`) and use `{% block %}` for `title`, `content`,
  `extra_css`, `extra_js`.
- Reusable UI goes in `templates/components/` and is included via
  `{% include %}` — no duplicated markup.
- Tailwind CSS throughout. Keep custom CSS in `static/css/` and JS in
  `static/js/` — no inline styles or inline `<script>` blocks.
- Accessibility: `alt` text on images, `<label>` linked to inputs via
  `for`/`id`, `aria-*` attributes, semantic HTML5 elements.
- Django auto-escapes output; never use `|safe` on user-generated content.
- Flash messages: use the Django messages framework, rendered by
  `templates/components/messages.html`.

## Performance

- Paginate all list views; never hand unbounded querysets to templates.
- `select_related` / `prefetch_related` on FK/M2M lookups; use
  `only()` / `defer()` to trim fields. Profile with django-debug-toolbar locally.
- Use `bulk_create` / `bulk_update` for batch operations (seeding, imports).
- Add DB indexes on fields used in `filter()` / `order_by()` / joins.
- AI generation is batched and retried (see `AI_GENERATION_BATCH_SIZE`,
  `AI_GENERATION_MAX_ATTEMPTS`); don't bypass those settings.

## Testing

- `pytest` (pytest-django) — `pytest.ini` points at `config.settings.local`.
  Run `pytest` from the project root.
- Root `conftest.py` defines shared fixtures: `student`, `professor`,
  `chairperson`, `subject`, `topic`, `mcq_question`, `numeric_question`,
  `teaching_assignment`, `program_section`, `academic_year`, etc. Reuse them;
  add new reusable fixtures there instead of duplicating setup in tests.
- Mirror the app layout: `apps/<app>/tests/test_<area>.py`. Use factory_boy
  when the conftest fixtures don't cover the shape you need.
- Name tests descriptively: `test_user_cannot_publish_others_article`.
- After any model/service change, add or update tests and run the full suite
  before declaring the task done.

## Code style (ruff)

- Ruff is installed; run `ruff check .` and `ruff format .` before finishing.
- PEP 8, max line length 88, import order: stdlib → third-party → local.
- Type hints on all function signatures; f-strings over `.format()` / `%`.
- Docstrings for public functions, classes, and modules.
- No unused imports, no commented-out code in version control.

## Security

- Never commit `.env`, API keys, or secrets — they live in `.env` only.
- Keep `config/settings/production.py` hardened: `DEBUG=False`,
  `SECURE_SSL_REDIRECT`, secure cookies, `X_FRAME_OPTIONS = "DENY"`.
  Don't weaken it.
- Validate every user input through forms; never trust raw request data.
- Role-check every protected view; scope every query to the current user's
  department/program.

## Git

- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- Never commit `.env`, `*.pyc`, `__pycache__/`, `media/`, or `db.sqlite3`.
- Review migrations before committing; squash when needed.

## Useful commands

- `python manage.py seed_examiq` — demo users and data
- `python manage.py runserver` — local dev at http://127.0.0.1:8000
- `pytest` — full test suite
- `ruff check .` / `ruff format .` — lint and format
- Demo credentials are listed in `README.md`.
