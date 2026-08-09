# AI Rate-Limit & Generation-Reliability Fixes

## Context

The deployed app (Railway) generates questions through the AI subsystem in `apps/ai/`. The deployed config was `LLM_PROVIDER=ollama` against **Ollama Cloud free tier**, which hit its request cap mid-batch. Symptoms: generation jobs stop, `AIServiceUnavailableError` aborts the whole job, and a 429 triggers a retry storm across the entire discovered Ollama model catalog.

Root causes to fix:
1. `run_question_generation_job` makes one API call per question (`count=1` × N) → ~20 requests per "generate 10" (plus 1 uncached `GET /api/tags` per call).
2. `ollama_client.list_available_models()` is uncached (Gemini caches 1h).
3. `ollama_client.chat_with_fallback` retries 3× per model **and iterates every discovered model** on 429/quota → request storm.
4. No retry/backoff at the job level → a single transient 429 fails the whole batch.
5. (Defensive) `openai_provider._chat` hardcodes `max_tokens=500` (truncates question JSON) and `OpenAIQuestionGenerator` silently returns fake stub questions on API failure.

**Decision (confirmed with user):** deployment switches to **Gemini free direct** (`LLM_PROVIDER=gemini`) — the Gemini client already has 1h model cache, per-model retry, retry-delay parsing, and `json_mode`. The Ollama/OpenAI client fixes are still implemented as defensive work for local dev and future paths.

## Goal

A professor generating up to 10 questions (easy/medium/hard) gets all 10 with no truncated/invalid output, using 2 API calls instead of ~20, with job-level retry on transient provider failures, and a clear FAILED error message (never silent fake questions) when a provider is genuinely down.

## Decisions

- **Batch size:** 5 questions per provider call (`AI_GENERATION_BATCH_SIZE=5`). Safe under the `GEMINI_QUESTION_MAX_OUTPUT_TOKENS=2048` cap: 5 questions ≈ 1400 tokens, 1890 for hard. "Generate 10" = 2 calls. If the default is changed above 7, hard-difficulty batches risk truncation.
- **Retry:** up to `AI_GENERATION_MAX_ATTEMPTS=3` per chunk, exponential backoff `sleep(min(2**attempt, 8))`. Only retry errors marked `retryable=True`; non-retryable errors (bad key, model not found) fail immediately.
- **Retryability:** add a `retryable: bool` attribute to `AIServiceUnavailableError` (default `False`). Providers set it from their existing `_is_retriable()` logic (429/quota/5xx/timeout → True; 404/auth → False).
- **429 behavior in `ollama_client`:** on rate-limit/quota errors, break out of the model loop immediately (no fallback-model iteration); keep per-model retries + fallback only for 5xx/connection/timeout.
- **`gemini_client` behavior unchanged** (existing test asserts fallback on quota); only add the `retryable` flag on the raised exception so job-level retry kicks in.
- **OpenAI generator:** mirror Gemini — use computed token budget with escalation `[max_tokens, min(max_tokens*2, 4096)]`, raise `AIServiceUnavailableError(retryable=True)` on API failure instead of stub fallback, raise on JSON parse failure after budgets exhausted, return `[]` for `topic is None` (matches Gemini and keeps existing `generate(None, ...) == []` tests passing).
- **Out of scope:** OmniRoute integration, Retry-After header parsing, preserving partial variations on job failure, changing the `LLM_PROVIDER` default in `base.py` (switch happens via env).

## Tasks (ordered)

### 1. `apps/ai/exceptions.py`
Add `retryable: bool = False` keyword param to `AIServiceUnavailableError.__init__`; store as `self.retryable`. Keep `message`/`detail` as-is.

### 2. `config/settings/base.py`
Add next to the LLM settings (after `GEMINI_QUESTION_MAX_OUTPUT_TOKENS`):
```python
AI_GENERATION_BATCH_SIZE = env.int("AI_GENERATION_BATCH_SIZE", default=5)
AI_GENERATION_MAX_ATTEMPTS = env.int("AI_GENERATION_MAX_ATTEMPTS", default=3)
```

### 3. `apps/ai/job_services.py` — batching + retry
- Add `import time` and `from django.conf import settings`.
- Add helper: `def _chunk_sizes(total: int, size: int) -> list[int]` returning `[min(size, total - start) for start in range(0, total, size)]`.
- Replace the generation loop (lines ~74–88) with:
  - `batch_size = getattr(settings, "AI_GENERATION_BATCH_SIZE", 5)`, `max_attempts = getattr(settings, "AI_GENERATION_MAX_ATTEMPTS", 3)`.
  - Iterate `for chunk in _chunk_sizes(job.count, batch_size)`. For each chunk, attempt up to `max_attempts` times:
    - `batch = normalize_generated_questions(generator.generate(topic, job.difficulty, count=chunk, source_material=source_material))`
    - `variations.extend(batch)`; break out on success.
    - On `AIServiceUnavailableError as exc`: if `not exc.retryable` → re-raise immediately; else increment attempt and `time.sleep(min(2**attempt, 8))` before retrying; after exhausting attempts, re-raise the last exception.
    - After a chunk succeeds, `if len(variations) >= job.count: break` (preserves existing termination semantics).
  - Remove the `# One question per provider call` comment; replace with a comment explaining batching to reduce API request count and the retry/backoff rationale.
- Keep the existing outer `try/except` (FAILED + `error_message`) and `finally: close_old_connections()` untouched.

### 4. `apps/ai/providers/ollama_client.py` — cache + stop 429 storm
- Add `import hashlib` and `from django.core.cache import cache`; add `CACHE_TTL_SECONDS = 3600`.
- Add `_cache_key()` hashing `settings.OLLAMA_API_KEY` (mirror `gemini_client._cache_key`).
- `list_available_models(force_refresh=False)`: check `cache.get(_cache_key())` first; on successful discovery, `cache.set(key, models, CACHE_TTL_SECONDS)`.
- Add `_is_rate_limit(exc)` helper matching `("429", "quota", "rate limit", "too many")`.
- In `chat_with_fallback`: restructure so that when `_is_rate_limit(exc)` fires, break the inner attempt loop **and** the outer model loop immediately (use a `rate_limited` flag). Keep `_is_not_found` break and per-model retry for other retriable errors unchanged.
- Final raise becomes: `raise AIServiceUnavailableError(_user_facing_message(last_error), detail=detail, retryable=_is_retriable(last_error))` (import/reference `_is_retriable` — it exists).

### 5. `apps/ai/providers/gemini_client.py`
Final raise in `chat_with_fallback` becomes:
`raise AIServiceUnavailableError(user_message, detail=detail, retryable=_is_retriable(last_error))`.
No other behavior changes.

### 6. `apps/ai/providers/openai_provider.py`
- `_chat(prompt, system="...", max_output_tokens: int = 500)`; pass `max_tokens=max_output_tokens` to `client.chat.completions.create` (keep `temperature=0.3`). Existing positional callers unchanged.
- Rewrite `OpenAIQuestionGenerator.generate`:
  - `topic is None` → `return []`.
  - Build `system, user_prompt, max_tokens` from `build_question_generation_prompt`; `budgets = [max_tokens, min(max_tokens * 2, 4096)]`.
  - For each budget: `raw = _chat(user_prompt, system=system, max_output_tokens=budget)`.
    - `raw is None` → raise `AIServiceUnavailableError("AI service is temporarily unavailable. Please try again later.", retryable=True)`.
    - Parse JSON with the existing regex; on success `return normalize_generated_questions(data[:count])`; on `json.JSONDecodeError`/`TypeError` log and try next budget.
  - After budgets exhausted → raise `AIServiceUnavailableError("AI returned incomplete or invalid JSON. Try again with fewer questions.", detail=..., retryable=True)`.
  - Remove the `StubQuestionGenerator` fallback path entirely (imports of `StubQuestionGenerator` still needed for other classes in the file — keep the import if still used, e.g. by `OpenAIDifficultyTagger`/`OpenAIQuestionValidator`).

## Tests

### 7. New/updated tests
- `apps/ai/tests/test_ollama_client.py`:
  - Add `test_list_available_models_caches`: distinct API key (e.g. `"cache-key"`), patch `urllib.request.urlopen`, call `list_available_models()` twice, assert `urlopen` called once. Delete the cache key in teardown (`cache.delete(...)`) to avoid cross-test collisions.
  - Add `test_rate_limit_does_not_try_fallback_models`: settings with primary `gpt-oss:120b` + fallback `gpt-oss:20b`, patch `list_available_models` → `[]`, patch `_chat_with_model` → `RuntimeError("HTTP 429: rate limit")`, patch `time.sleep`. Assert `AIServiceUnavailableError` raised, `retryable is True`, message contains "rate limit", `_chat_with_model.call_count == 1`.
  - Existing tests (`test_fallback_model_on_failure` with 503, `test_skips_retries_on_404`) must still pass.
- `apps/ai/tests/test_gemini_client.py`: in the existing all-fail test, assert the raised exception's `retryable` matches `_is_retriable(last_error)` (add assertion to the "raises when all fail" test).
- New `apps/ai/tests/test_job_services.py` (create `AIGenerationJob` directly with `created_by`/`course_id`/`topic_id`/`difficulty`/`count`/`source_material`; patch `apps.ai.job_services.get_question_generator` and `apps.ai.job_services.time.sleep`):
  - `test_batches_generation_calls`: `count=10`, batch size 5 → `generate` called twice with `count=5`, job SUCCEEDED.
  - `test_retries_retryable_failure_then_succeeds`: generate raises `AIServiceUnavailableError(retryable=True)` once then returns a batch → 2 calls, SUCCEEDED.
  - `test_retryable_failure_exhausts_and_fails`: always raises retryable → `AI_GENERATION_MAX_ATTEMPTS` calls, job FAILED.
  - `test_non_retryable_failure_fails_immediately`: raises `retryable=False` → 1 call, job FAILED, `error_message` surfaced.
- `apps/ai/tests/test_factory.py`: add `test_openai_generator_raises_on_api_failure` (topic not None, `_chat` → None ⇒ `pytest.raises(AIServiceUnavailableError)`) and `test_openai_generator_raises_on_invalid_json` (`_chat` → `"not json"` ⇒ raises).
- `apps/questions/tests/test_ai_generate_view.py`: patch `apps.ai.job_services.time.sleep` in `test_enqueues_job_and_surfaces_ai_error` (its message contains "quota" → retryable → 3 attempts before FAILED; assertion `job.status == FAILED` and the surfaced message still hold). Optionally assert `generator.generate.call_count == 3`.

### 8. Validation commands
- `pytest apps/ai apps/questions/tests/test_ai_generate_view.py apps/analytics/tests/test_professor_platform.py` (settings: `config.settings.local` via `pytest.ini`).
- Full `pytest` (ensure no regressions in `apps/analytics`, `apps/reviews`).
- Manual smoke: set `LLM_PROVIDER=gemini` locally, `runserver`, professor uploads a module, generate 10 easy and 10 hard, poll status → 10 variations each, no `ai_error`. Confirm logs show `Gemini success` and no 429 retry storm.

## Rollout (deployment)

1. `.env` (gitignored): set `LLM_PROVIDER=gemini`. Keep `GEMINI_API_KEY`. Ollama/OpenAI keys can stay (unused).
2. **Verify `GEMINI_API_KEY` validity first** — the current value starts with `AQ.`; Google AI Studio keys normally start with `AIza`. If invalid, create a new key at aistudio.google.com and re-test generation locally before deploying. (Treat this as a blocking rollout check.)
3. Railway env vars: set `LLM_PROVIDER=gemini`, `GEMINI_API_KEY=<valid key>`, keep `AI_ENABLED=True`. New settings default fine (`AI_GENERATION_BATCH_SIZE=5`, `AI_GENERATION_MAX_ATTEMPTS=3`).
4. Deploy and verify via Railway logs: generation job completes with `Gemini success` entries; a "generate 10" action now produces 2 API calls; no 429 failures. Since batches complete in seconds, the Railway free-tier sleep window no longer kills in-progress jobs.

## Risks / notes
- OpenAI generator behavior change (stub → raise) only affects the currently-unused `LLM_PROVIDER=openai` path; covered by updated tests.
- Job-level retry adds up to ~14s latency on transient failures (background thread; status poll shows RUNNING) — acceptable.
- Partial variations are still discarded when a job FAILs (e.g., 5 of 10 generated before an unrecovered quota error). Preserving partials is deliberately out of scope.
- `normalize_generated_questions` is applied both in the providers and in `job_services` (existing double-normalization; unchanged).
- Ollama model-discovery cache is keyed by API-key hash; use `force_refresh=True` if a model list changes.
