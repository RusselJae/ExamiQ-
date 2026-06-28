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
