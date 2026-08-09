# Two UI Refinements

## 1. Professor student view: use same chart as student dashboard

The student dashboard uses `renderOverviewTrendsChart` (from `static/js/overview-trends-chart.js`) — a single paginated line chart with a metric selector dropdown toggling between confidence and mistakes. The professor student detail currently uses 3 separate chart cards (score trend, confidence, mistakes). Replace with the same single-chart-with-selector pattern, and drop the score trend entirely.

### Data shape needed by `renderOverviewTrendsChart` (flat mode)
```json
{
  "confidence": [{"label": "1st (10-09-2026)", "value": 2.3}],
  "mistakes": [{"label": "1st (10-09-2026)", "value": 3}]
}
```
This matches `student_dashboard_trends()` output. The summary's `session_metrics_series` already has per-session `avg_confidence` and `mistakes`, but labels are topic names (not ordinal+date). Need to build the overview-trends-compatible dict from the session data already in `_build_student_activity_summary`.

### Changes

**`apps/analytics/services.py` — `_build_student_activity_summary`**
- Add `dashboard_trends` key: build `{"confidence": [{label, value}], "mistakes": [{label, value}]}` from the same `session_list` used for `session_metrics_series`, using ordinal+date labels (same pattern as `student_dashboard_trends()`). Reuse `_ordinal_label()` and `confidence_to_scale_0_3()`.
- Remove `score_trend` and `session_metrics_series` keys (no longer needed by templates).

**`templates/analytics/professor/partials/student_detail_dashboard.html`**
- Remove the 3-card `student-chart-grid` (score trend, confidence, mistakes).
- Replace with a single `bento-card` matching the student dashboard pattern:
  - Metric selector `<select>` (confidence / mistakes)
  - `<canvas>` for `renderOverviewTrendsChart`
  - Empty state + pager buttons
- Keep session history table unchanged below.

**3 detail templates** (`student_detail.html`, `section_student_detail.html`, `professor_student_detail.html`)
- Replace the 3-chart init JS with single `renderOverviewTrendsChart` call (matching student dashboard wiring pattern).

**`static/js/examiq-ui.js`**
- Remove `renderSessionConfidenceChart` and `renderSessionMistakesChart` (now unused).

**`static/css/custom.css`**
- Remove `.student-chart-grid` and its media query (no longer used).

### Validation
- `pytest apps/analytics/tests/ apps/questions/tests/test_ai_generate_view.py -q`

---

## 2. Add Questions: selection field instead of card grid

Replace the card grids in both `add_hub.html` and `batch_form.html` hub_mode block with a compact `<select>` dropdown that navigates on change.

### Changes

**`templates/professor/questions/add_hub.html`**
- Replace the `hub-course-grid` card grid with a `<select>` inside a `bento-card`:
  - Label "Course subject"
  - `<option>` for each course option showing "CODE — Name (Year · Semester)"
  - `onchange` navigates to `?course=pk`
  - Empty-state message when no options.

**`templates/professor/questions/batch_form.html`** (hub_mode block)
- Replace the `hub-course-grid` with the same `<select>` pattern, with `selected` on the current course.

**`static/css/custom.css`**
- Remove `.hub-course-grid`, `.hub-course-card`, `.hub-course-card--active`, `.hub-course-card__badge`, `.hub-course-card__name`, `.hub-course-card__meta` rules (no longer used).

### Validation
- `pytest -q` on modified test files; manual visual check.
