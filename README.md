# EXAMIQ

Self-regulated mathematics exam review system for college students.

## Features

- **Students**: Confidence-based timed review sessions, adaptive question selection, calibration summaries, rule-based review recommendations, mistake tracking, performance dashboards
- **Professors**: Course-level analytics, intervention lists with CSV export, confidence trends, mistake patterns
- **Chairpersons**: Program-level monitoring, question approval, anonymized research CSV export, institutional reporting
- **Roles**: Student, Faculty, Chairperson, Campus Administrator

## Quick Start

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements/local.txt
copy .env.example .env
python manage.py migrate
python manage.py seed_examiq
python manage.py runserver
```

### OCR (scanned learning materials)

Faculty-uploaded PDFs with image-only (scanned) pages are transcribed with
Tesseract OCR when available. Install the Tesseract binary on the host:

- Windows: download from https://github.com/UB-Mannheim/tesseract/wiki and add to PATH
- macOS: `brew install tesseract`
- Debian/Ubuntu: `sudo apt install tesseract-ocr`

When Tesseract is missing, the app degrades gracefully (text-layer pages still
work; scanned pages fall back to a "proceed anyway" option in the UI).

Visit http://127.0.0.1:8000 and sign in with demo credentials.

## Demo Credentials

| Role | Email | Password | Notes |
|------|-------|----------|-------|
| Chairperson (CS) | chair.computersci@examiq.edu | demo1234 | Programs, question review, research export |
| Chairperson (Education) | chair.collegeofedu@examiq.edu | demo1234 | Education department scope |
| Professor | prof.algebra@examiq.edu | demo1234 | CS course offerings |
| Professor | prof.calculus@examiq.edu | demo1234 | Multi-program courses |
| Student (trends) | student1@examiq.edu | demo1234 | Multi-date accuracy chart |
| Student (misconception) | student3@examiq.edu | demo1234 | High-confidence wrong answers |
| Student (low practice) | student5@examiq.edu | demo1234 | Weak accuracy, old sessions |
| Admin | admin@examiq.edu | admin1234 | Django admin |

## AI Configuration

Set in `.env`:

```env
AI_ENABLED=True
LLM_PROVIDER=ollama   # ollama (cloud), gemini, or openai

# Ollama Cloud — https://ollama.com/settings/keys
OLLAMA_API_KEY=your-key
OLLAMA_BASE_URL=https://ollama.com
OLLAMA_MODEL=gpt-oss:120b

# Gemini
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-2.0-flash
```

Question Bank shows **AI: Ollama Cloud**, **AI: Gemini**, **AI: OpenAI**, or **AI: Off** based on configuration.

## Learning Material Editing

Two editors, chosen automatically per material:

| Editor | Used for | Needs |
| --- | --- | --- |
| **Built-in HTML editor** | Everything, unless ONLYOFFICE is on | Nothing |
| **ONLYOFFICE** | `.docx`, `.doc`, `.odt`, `.rtf`, `.xlsx`, `.pptx` | A running Document Server |

The built-in editor stores editor HTML and re-exports it, so a complex Word file
loses some fidelity. ONLYOFFICE round-trips the real binary file and keeps
headings, styles, headers and tables intact.

### ONLYOFFICE Document Server

Leave `ONLYOFFICE_DOCUMENT_SERVER_URL` blank and nothing changes — the built-in
editor is used for every material.

```env
ONLYOFFICE_DOCUMENT_SERVER_URL=https://onlyoffice.example.com
ONLYOFFICE_JWT_SECRET=a-long-random-shared-secret
ONLYOFFICE_JWT_ENABLED=True
```

Run the server as its own service (it cannot live inside a Nixpack):

```bash
docker run -d --name onlyoffice -p 8080:80 \
  -e JWT_ENABLED=true -e JWT_SECRET=a-long-random-shared-secret \
  -e JWT_HEADER=Authorization \
  -v /data/onlyoffice:/var/www/onlyoffice/Data \
  onlyoffice/documentserver
```

**The Document Server must be able to reach this app directly.** It calls back to
`/professor/courses/<id>/materials/<id>/office/callback/` server-to-server, so
the app needs a public hostname in production — not just a browser-reachable one.

Security notes:

- Editor config and every callback are JWT-signed; a callback with a missing or
  invalid token is rejected.
- The Document Server fetches the file through a signed, short-lived,
  path-bound token instead of a session cookie.
- Edited files are only downloaded from the Document Server's own origin, so the
  callback cannot be used as an SSRF proxy.

**PDFs always use the built-in editor.** A PDF has no paragraph model, so making
one editable means a lossy PDF→DOCX conversion (`pdf2docx` or LibreOffice
headless) first. Large scanned PDFs convert slowly and need manual cleanup, so
this is not done automatically.

## Email (Brevo SMTP)

Signup OTP and workflow emails use Django SMTP. Copy keys from `.env.example` into `.env`:

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-brevo-smtp-login
EMAIL_HOST_PASSWORD=your-brevo-smtp-key
DEFAULT_FROM_EMAIL=ExamiQ <your-verified-sender@example.com>
```

`DEFAULT_FROM_EMAIL` must be a sender verified in Brevo. Pytest uses the locmem backend and does not call Brevo.

## Running Tests

```bash
pytest
```

## Pilot Study

See [docs/thesis/pilot-protocol.md](docs/thesis/pilot-protocol.md) for survey items, export columns, and panel demo script.

## Tech Stack

- Django 5 + django-allauth
- Tailwind CSS + HTMX + KaTeX + Chart.js
- OpenAI / Google Gemini (optional)
- SQLite (dev) / PostgreSQL (production)
