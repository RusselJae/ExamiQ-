# EXAMIQ Pilot Study Protocol

## Purpose

Evaluate whether confidence-rated review sessions improve calibration awareness and self-regulated learning (SRL) among college students.


## Timed exam mode

Students in **timed exam** mode answer questions with a per-question countdown (default 30 seconds, configurable per review window). Explanations appear on the session summary after the exam ends — not inline during the exam. Confidence ratings are omitted in timed exam mode.

## Participant flow (updated)

1. Student logs in and sets home degree program in **Profile**
2. Optional: submit **Pilot Study consent** checkbox
3. Complete **pre-survey** (Likert 1–5) anytime from Profile
4. Use EXAMIQ for review sessions during the pilot period
5. Submit **post-survey** anytime from Profile (no session gate)

## Survey Items

All items use a 1–5 Likert scale (1 = strongly disagree, 5 = strongly agree).

### Pre-study

| Field | Prompt |
|-------|--------|
| `calibration_awareness` | I am aware of how confidence affects learning |
| `confidence_rating_usefulness` | Rating confidence after each answer is useful |
| `would_recommend` | I would recommend EXAMIQ to classmates |
| `open_feedback` | Optional free text |

### Post-study

| Field | Prompt |
|-------|--------|
| `calibration_awareness` | EXAMIQ helped me understand my calibration gaps |
| `confidence_rating_usefulness` | Confidence ratings improved my self-regulated learning |
| `would_recommend` | I would recommend EXAMIQ after using it |
| `open_feedback` | Optional free text |

## Research Export (Chairperson)

**URL:** `/chairperson/research/export/`

Department-scoped, anonymized CSV. Columns:

| Column | Description |
|--------|-------------|
| `student_hash` | SHA-256 hash (first 16 chars), no PII |
| `program` | Home degree program slug |
| `sessions_completed` | Completed review sessions |
| `total_answers` | All answers submitted |
| `accuracy_pct` | Overall accuracy |
| `avg_confidence` | Mean confidence (1–5) |
| `mastery_count` | High confidence + correct |
| `misconception_count` | High confidence + wrong |
| `lucky_guess_count` | Low confidence + correct |
| `expected_gap_count` | Low confidence + wrong |
| `uncertain_count` | Medium confidence answers |
| `mistake_records` | Logged mistakes |
| `pre_*` / `post_*` | Survey Likert scores |

## Professor Interventions Export

**URL:** `/professor/courses/<pk>/interventions/export/`

Per-course CSV with student name, intervention flags, accuracy, and suggested actions.

## 5-Minute Panel Demo Script

1. **Student** (`student3@examiq.edu` / `demo1234`) — finish a review, show session summary calibration + recommended topic
2. **Professor** (`prof.algebra@examiq.edu`) — MATH101-CS course detail → intervention list flags student3 → download CSV
3. **Chairperson** (`chair.computersci@examiq.edu`) — approve pending question → Programs dashboard → download research CSV
4. **Profile** — show pre/post survey submission
5. **Question Bank** — Generate Variations (Gemini if `LLM_PROVIDER=gemini` and key set)

## Demo Logins

| Role | Email | Password |
|------|-------|----------|
| Chair (CS) | chair.computersci@examiq.edu | demo1234 |
| Chair (Education) | chair.collegeofedu@examiq.edu | demo1234 |
| Professor | prof.algebra@examiq.edu | demo1234 |
| Student (misconception) | student3@examiq.edu | demo1234 |
| Student (low practice) | student5@examiq.edu | demo1234 |
