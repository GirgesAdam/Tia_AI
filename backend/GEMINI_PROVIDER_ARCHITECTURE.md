# Tia AI — Gemini Provider Architecture

## Model roles

- Main customer agent:
  - primary: `gemini-3.7-flash`
  - fallback: `gemini-3.6-flash`
  - thinking: `low`
- Semantic capability router:
  - primary: `gemini-3.7-flash`
  - fallback: `gemini-3.6-flash`
  - thinking: `low`
- Active workflow interpreter:
  - primary: `gemini-3.7-flash`
  - fallback: `gemini-3.6-flash`
  - thinking: `low`
- AI-assisted onboarding:
  - primary: `gemini-3.7-flash`
  - fallback: `gemini-3.6-flash`
  - thinking: `medium`
- Background utility work:
  - `gemini-3.5-flash-lite`
  - thinking: `minimal`
- Future embeddings:
  - `gemini-embedding-001`

## Realtime latency architecture

Realtime customer turns optimize the orchestration before changing model
quality:

1. The semantic router or active-flow interpreter decides capabilities and
   safety state.
2. Safe PostgreSQL reads are prefetched deterministically when the semantic
   state already provides enough arguments. This removes an otherwise redundant
   LLM round whose only job would be choosing the same read tool. Booking prefetch
   can resolve the AI-extracted service, branch, and doctor entities in one
   PostgreSQL-backed `get_booking_options` call; ambiguous doctor matches are
   returned as bounded choices instead of guessed.
3. Prefetched results are injected as hidden source-of-truth operational
   context and the already-executed read tool is removed from that turn's tool
   exposure so it is not called twice.
4. The LangGraph customer agent is bounded to `AGENT_MAX_TOOL_ROUNDS` (default
   `2`). If the budget is exhausted, an unbound finalizer must answer from
   existing tool results or ask for genuinely missing information.
5. `AGENT_RECURSION_LIMIT` is a safety ceiling (default `8`), not the primary
   loop-control mechanism.
6. Runtime logs emit per-provider-call, semantic-stage, prefetch, tool-round,
   customer-agent, and total-turn durations.

No write tool is ever prefetched. Booking/reschedule writes remain governed by
persisted workflow state and deterministic write authorization.

## Runtime retry and failover policy

Realtime calls use `LLM_REALTIME_MAX_RETRIES=0`. The primary gets one provider
request only; a provider-side 5xx immediately moves to the configured fallback
instead of spending customer-visible latency retrying the same overloaded model.

Tia then performs at most one cross-model failover for each individual model
request:

- HTTP `5xx` -> try that role's configured `gemini-3.6-flash` fallback once.
- HTTP `400/401/403/404` -> surface the provider failure; do not switch models.
- HTTP `429` -> surface the rate/quota failure; do not switch models.

The failover wraps one LLM request only. Tia never replays an entire LangGraph
run, so a successful database/tool write cannot be repeated merely because a
later model call encountered a provider outage.

Onboarding remains less latency-sensitive and keeps the normal
`LLM_MAX_RETRIES` policy before its configured 5xx-only fallback.

Fallbacks can be disabled independently by setting the corresponding env value
to an empty string:

```text
GEMINI_AGENT_FALLBACK_MODEL=
GEMINI_ROUTER_FALLBACK_MODEL=
GEMINI_FLOW_FALLBACK_MODEL=
GEMINI_ONBOARDING_FALLBACK_MODEL=
```

## Structured output

Router and active-flow interpreter use Gemini-native JSON Schema structured
output through `ChatGoogleGenerativeAI.with_structured_output(...,
method="json_schema")`.

The returned object is validated again with the local Pydantic schema. Local
schema/validation failures are not treated as provider-capacity failures and do
not trigger cross-model failover.

## What remains product architecture

- semantic multi-capability routing
- no keyword intent routing
- persisted/versioned conversation workflows
- deterministic capability -> tool policy
- write authorization guardrails
- medical risk override and human handoff
- PostgreSQL business-rule validation
- bounded LangGraph tool orchestration

## API key

Keep `GEMINI_API_KEY` only in `backend/.env`. Never expose it to the frontend.


## Outbound delivery retry ownership

PostgreSQL is the retry source of truth for channel delivery. n8n performs one
provider send attempt for each claimed dispatch and reports the real provider
result back to Tia. `CHANNEL_DISPATCH_MAX_ATTEMPTS` defaults to `5`; exhausted
queued/stale-processing dispatches are terminally failed instead of retrying
indefinitely. Provider error text is preserved in `last_error` when available.
