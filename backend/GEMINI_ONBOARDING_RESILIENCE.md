# Tia v0.16.4 — Gemini onboarding resilience

AI onboarding keeps `gemini-3.7-flash` as its primary production model.

`ChatGoogleGenerativeAI` remains responsible for the configured provider
retry policy (`LLM_MAX_RETRIES`). Tia does not add sleeps or duplicate
exponential-backoff loops around every request.

After the primary client's retries are exhausted:

- HTTP 5xx / capacity failure -> one attempt on `gemini-3.6-flash`.
- HTTP 400/401/403/404 -> surface the error; no fallback.
- HTTP 429 -> surface the quota/rate-limit failure after normal client
  retries; no cross-model quota workaround.

This is a bounded availability policy, not a free-tier workaround.
The fallback is the previous stable Flash generation and uses the same:

- compact provider DTO
- canonical Gemini JSON Schema
- full local Pydantic validation
- deterministic onboarding business validation
- explicit Admin confirmation
- atomic PostgreSQL execution

Set `GEMINI_ONBOARDING_FALLBACK_MODEL=` to disable failover.
