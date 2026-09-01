# Tia v0.19.3 — Realtime Reliability & Latency

This patch keeps the existing Conversation Flow contract unchanged. It changes only realtime model availability/latency policy and the clinic catalog eligibility filter.

## Realtime model strategy

Unified interpreter:

`gemini-3.5-flash-lite -> gemini-3.6-flash -> gemini-3.5-flash`

Grounded response composer:

`gemini-3.5-flash-lite -> gemini-3.6-flash`

Legacy realtime customer-agent/router/flow rollback path:

`gemini-3.6-flash -> gemini-3.5-flash`

Gemini 3.7 Flash is no longer on the realtime customer critical path. Onboarding settings are intentionally unchanged.

The interpreter and composer use `thinking_level=minimal`; the legacy customer-agent path remains `low`. Same-model realtime retries remain disabled.

## Per-model circuit breaker

Provider 5xx opens a circuit for the failing model only. Later realtime calls bypass every model whose circuit is still open and continue through the configured chain. 4xx and 429 never switch models.

Example after two provider capacity failures:

`Flash-Lite 503 -> 3.6 503 -> 3.5 success`

The next turn during cooldown becomes:

`skip Flash-Lite -> skip 3.6 -> 3.5`

No workflow or database write is replayed.

## Active clinic catalog

The LLM catalog still comes directly from PostgreSQL. A doctor is now included only when the doctor/staff are active, booking is enabled, and the doctor has at least one active service assignment and one active branch assignment whose service/branch is itself active.

There is no keyword routing, regex matching, fuzzy name mapping, or alias table in this change. Natural-language entity understanding remains the Unified LLM's job; Python validates canonical IDs and executes deterministic policy/database operations.
