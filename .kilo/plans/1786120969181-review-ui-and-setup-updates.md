# Review UX + Setup Updates

Note: the attached `image.png` could not be read (model does not support image input); this plan is based solely on the written task list.

## Tasks
1. AI Tutor modal: remove "Show step" reveal; solution shows automatically on open.
2. Polish UI/UX of Solution / AI Conversation / Faculty Conversation tabs (readable, modern, clean).
3. Session Complete heatmap strip: solid confidence colors instead of light pastels.
4. Student dashboard: match Study Plan column height to the trends line chart.
5. Remove year level & section from student profile (and signup); drop the exam eligibility gate on them.
6. Start Review: add "Select all" for courses; each selected course gets >=3 questions (randomized), single course max 20, all-course total max 70.

---

## 1. AI Tutor — remove progressive "Show step"

**File: `static/js/ai-tutor-modal.js`**
- `renderFeedbackPanel()` (~line 520): change `progressive: true` -> `progressive: false` in the `renderTutorVisualResponse` call for the Solution panel.
- `renderMessages()` (~line 571): change `progressive: true` -> `progressive: false` in the assistant-message render.

Effect: `tutor-visual-response.js` paints all steps + final answer + chart immediately; the "Show first step"/"Show next step" button (`tutor-visual-next`) is never rendered. Solution tab is already the default screen on open (`preferredScreen || "solution"`), so the full solution now appears automatically.

No changes needed in `tutor-visual-response.js` (progressive machinery becomes dormant, harmless). The in-exam `explanation.html` "Reveal Next Step" flow is separate and untouched.

## 2. AI Tutor UI/UX polish (Solution / AI Chat / Faculty Chat)

Primary file: `static/css/custom.css`. Optional minor markup: `templates/reviews/partials/ai_tutor_modal.html`. Chat classes are shared with the faculty concern modal (`chat-*`), so the faculty conversation in both places improves together.

**Modal shell**
- Header: keep dark primary; add subtle gradient + rounded corners; keep close button.
- Tabs (`ai-tutor-modal__tab`): refine active pill (primary-soft bg, primary border, primary text — already exists; tighten padding/typography).

**Solution tab**
- `.ai-tutor-feedback-panel`: wrap content in a light surface (`#f8fafc`) rounded card with comfortable padding.
- `.ai-tutor-feedback-panel__stem`: ~1rem, weight 700, navy, line-height 1.5.
- `.ai-tutor-answer-compare__col`: white bg, 1px `#e2e8f0` border, `--radius-card`, soft shadow; add colored accent labels ("Your answer" coral, "Correct answer" green) and a correct/incorrect chip.
- `.tutor-visual-step`: icon circle solid `var(--color-primary)` with white number; step title 0.875rem/700; equations rendered as monospace chips (`background:#f1f5f9; border-radius:0.5rem; padding:0.35rem 0.6rem`).
- `.tutor-visual-why`: keep amber palette; refine radius/line-height.
- `.tutor-visual-answer`: success tint, circular check icon, cleaner spacing.

**Chat (AI + Faculty)**
- `.chat-thread`: subtle canvas background (`#f8fafc` or soft gradient), comfortable gap.
- `.chat-bubble--in`: white, 1px border, soft shadow, radius 1rem (0.35 top-left), max-width ~80%.
- `.chat-bubble--out`: solid `var(--color-primary)` (or subtle gradient), radius 1rem (0.35 top-right), max-width ~75%.
- `.chat-row__header`: 0.6875rem, slate-600, slight letter-spacing; timestamps lighter (`#94a3b8`).
- `.chat-avatar`: refined ring/border; keep AI purple (`#5b21b6`), self teal (`#0f766e`).
- `.chat-composer-wrap`: border-top, white bg; `.chat-composer` wrapped in a rounded bordered container; input borderless inside with focus ring; send button primary with hover state; attachment chip restyle.
- Keep changes CSS-only unless a tiny template tweak is needed.

## 3. Session Complete heatmap strip — solid colors

**File: `static/css/custom.css`** (session-strip section, ~lines 6679-6690).
- Replace the `.session-strip-cell.confidence-tier-badge--*` text-color-only overrides with solid backgrounds:
  - none: `#dc2626`, white text
  - low: `#f97316`, white text
  - average: `#eab308`, dark text (`#0f172a`) for contrast
  - high: `#16a34a`, white text
- Add matching solid swatches: `.session-strip-legend__swatch.confidence-tier-badge--none|low|average|high { background: ... }`.
- Do NOT touch the base `.confidence-tier-badge--*` classes (used as light text pills on `analytics/student/mistakes.html` and `post-session-feedback.js`). Mistakes cells (`--wrong #e53935`, `--correct #43a047`) already solid — leave them.

## 4. Student dashboard — Study Plan height matches line chart

**Files: `templates/analytics/student/dashboard.html`, `static/css/custom.css`.**
- Root cause: chart card is ~20rem chart + filters + pager; study-plan scroll area is capped by `.bento-card--list .bento-card-scroll { max-height: 240px }` leaving dead space at the bottom of the stretched card.
- Add class `study-plan-card` to the `span-3` study-plan card in dashboard.html and scope an override:
  - `.study-plan-card .bento-card-scroll { max-height: none; }`
- The card keeps `h-full flex flex-col`; the scroll div keeps `flex-1`, so the list fills the card height, which is stretched to equal the chart row. Other pages using `bento-card-scroll` (professor course/section/subject detail, summary.html) keep the 240px cap.

## 5. Remove year level & section from student profile + signup; drop eligibility gate

Keep the `User.year_level` / `User.section` model FK fields (campus/professor roster, section heatmap, SectionExamSetup flows still use them). Remove self-service collection and exam gating only.

**`apps/users/forms.py`**
- `ExamiQSignupForm`: delete `year_level` + `section` field declarations; delete `clean_year_level()` and `clean_section()`; in `clean()` remove the section_obj block (keep student_number uniqueness); in `save()` remove `user.year_level = ...` and `user.section = ...`.
- `ProfileUpdateForm`: delete `year_level`/`section` declarations, the student branch setting initials, `clean_section()`, the year/section part of `clean()`, and the year_level/section assignment + `update_fields` entries in `save()`.
- Clean up imports: `parse_section_label`, `get_or_create_student_section`, and (already-unused) `section_matches_student`, `sections_for_student`, `validate_section_capacity` if no longer referenced in the file.

**`templates/account/signup.html`** — remove the year_level + section row (lines ~54-69) inside `#signup-student-fields`.

**`templates/users/profile.html`** — remove the year_level pill (~38-40) and section pill (~41-43); remove the year_level/section form block (~66-75); remove the section-cascade JS block (~249-278).

**`apps/reviews/exam_setup_services.py`**
- `student_setup_eligibility()`: drop the section / year_level / year_mismatch checks and the `section_exam_setup_for_student` disabled check. Keep program (BSED Math) + `program_has_approved_questions()` checks.
- `subjects_available_for_student()`: return the full BSED Math subject queryset (drop the section-restriction path).
- Remove `section_exam_setup_for_student()` if it becomes unused.

**`templates/reviews/setup.html`** — update the "How it works" callout (remove "year and section stay on your profile"); simplify the ineligibility card (drop the "Update Profile" link since section/year reasons no longer exist).

**Tests**
- `apps/users/tests/test_signup.py`: `_student_data` drops year/section keys; `test_student_signup_creates_active_student` asserts `year_level is None` / `section is None`; delete `test_student_signup_creates_new_section_when_typed`; update `test_student_number_must_be_nine_digits` and remove the `"1M or BSE 2-1M"` assertion in `test_signup_page_has_divider_and_placeholder`.
- `apps/users/tests/test_profile.py`: `test_update_name`, `test_update_middle_name`, `test_update_suffix`, `test_upload_profile_photo` currently FAIL (ProfileUpdateForm requires year_level for students) — the form change fixes them; strip the now-stale `"year_level"` key from `test_upload_profile_photo`.
- `apps/analytics/tests/test_nav_topics_exam_setup.py`: `test_enabled_setup_restricts_student_subjects` asserts section gating on `subjects_available_for_student` — change it to assert the open bank returns both subjects (or delete); keep `test_section_exam_setup_view_saves`.

## 6. Start Review — Select all + randomized per-course question counts

**`static/js/multi-select-dropdown.js`**
- Opt-in "Select all" row (only when root has `data-select-all`): checkbox + "Select all" at the top of the dropdown menu. Checking selects every option; unchecking clears. Keeps per-option checkboxes, trigger label ("All selected" when every option is checked), and chips in sync. Add `data-select-all="true"` to the setup.html multi-select wrapper. The professor `section_exam_setup.html` wrapper has no such attribute, so it is unaffected.

**`apps/reviews/exam_setup_services.py`** — rewrite `build_multi_subject_exam_target()`:
- New constants: `MIN_QUESTIONS_PER_SUBJECT = 3`, `MAX_TOTAL_QUESTIONS = 70`, `MAX_QUESTIONS_SINGLE_SUBJECT = 20` (keep `QUESTIONS_PER_SUBJECT` alias if referenced elsewhere, otherwise replace).
- Per subject: `avail = count_available_questions_for_subject(subject, difficulty)`; `floor = min(3, avail)`; `cap = min(20, avail)`; error if `avail == 0` (existing behavior).
- Single subject: `count = random.randint(floor, cap)`.
- Multiple subjects:
  - If `sum(caps) <= 70`: `count_i = random.randint(floor_i, cap_i)` for each (each >=3, total automatically <=70).
  - Else: start each subject at its floor, then randomly distribute `70 - sum(floors)` extra one-at-a-time across shuffled subjects up to `cap_i` (total exactly 70). Defensive: if `sum(floors) > 70` (unrealistic, >23 subjects), trim floors largest-first to 70.
- Build queue with `question_ids_for_subject(subject, difficulty, limit=count_i)`, shuffle the concatenated queue; `duration_minutes` from queue length (unchanged).

**`templates/reviews/setup.html`** — update subtitle + callout copy: at least 3 per course, up to 20 for a single course, max 70 total, counts randomized.

**Tests — `apps/reviews/tests/test_forms.py`**
- `test_caps_questions_per_subject`: change exact `== 30` assertion to per-subject counts in [3, 15], total == len(queue), total <= 70.
- Add `test_single_subject_capped_at_20` (1 subject, 25 questions -> count in [3,20]).
- Add `test_many_subjects_capped_at_70` (13 subjects x 15 questions -> total == 70, each subject >=3 and <=20).
- `test_queue_includes_ids_from_each_subject` (3x3) and `test_accepts_multi_subject_setup_when_questions_available` (3x2) still pass (deterministic: avail <= 3 -> floor == cap).

---

## Validation
- `venv\Scripts\python.exe -m pytest apps/reviews apps/users/tests apps/analytics/tests -q`
- Manual: complete a review -> Session Complete -> AI Tutor (all 3 tabs, full solution shown, no step buttons); student dashboard heights; profile page has no year/section; signup has no year/section; start review with "Select all" (>=3/course, total <=70; single course <=20).
