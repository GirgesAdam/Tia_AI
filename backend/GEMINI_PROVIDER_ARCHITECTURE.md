# Tia AI v0.14.4 — Gemini Provider Architecture

## Model roles

- Main customer agent:
  - `gemini-3.7-flash`
  - thinking: `medium`
- Semantic capability router:
  - `gemini-3.7-flash`
  - thinking: `low`
- Active workflow interpreter:
  - `gemini-3.7-flash`
  - thinking: `low`
- AI-assisted onboarding:
  - `gemini-3.7-flash`
  - thinking: `medium`
- Background utility work:
  - `gemini-3.5-flash-lite`
  - thinking: `minimal`
- Future embeddings:
  - `gemini-embedding-001`

## What was removed

The Groq Free-tier tuning is not part of Tia's product architecture and has
been removed:

- manual 429 Retry-After parsing/sleeps
- Groq SDK exception handling
- Groq-specific retry counts/backoff
- Groq strict-schema fallback chain
- 15-second regression cooldowns
- Free-tier booking compatibility artifacts/tests
- Groq-specific semantic-output budget docs/tests

## What remains

These are product architecture and are intentionally unchanged:

- semantic multi-capability routing
- no keyword intent routing
- persisted/versioned conversation workflows
- deterministic capability -> tool policy
- write authorization guardrails
- medical risk override and human handoff
- PostgreSQL business-rule validation
- LangGraph tool orchestration

## Structured output

Router and active-flow interpreter use Gemini-native JSON Schema structured
output through `ChatGoogleGenerativeAI.with_structured_output(...,
method="json_schema")`.

The returned object is validated again with the local Pydantic schema.

## Retries

`ChatGoogleGenerativeAI` owns normal request retries (`LLM_MAX_RETRIES=2`).

Tia does not implement provider-specific sleep/backoff loops and never retries a
whole LangGraph run, so successful tool writes are not replayed.

## API key

Keep `GEMINI_API_KEY` only in `backend/.env`. Never expose it to the frontend.
