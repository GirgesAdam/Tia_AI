# v0.16.2 — Gemini Structured Schema Compatibility

## Failure observed

AI-assisted onboarding reached Gemini 3.7 Flash but the native structured
request was rejected with HTTP 400 `INVALID_ARGUMENT` before any clinic write.

The onboarding schema is richer than Tia's router schema. Pydantic emits
keywords such as:

- `default`
- `pattern`
- `minLength` / `maxLength`
- `exclusiveMinimum`

Gemini Structured Outputs supports a documented subset of JSON Schema. Those
local validation keywords are not required for controlled generation.

## Provider boundary

Tia now maintains two representations intentionally:

1. **Local authoritative Pydantic schema**
   - regex constraints
   - length constraints
   - exclusive numeric bounds
   - cross-field validators
   - business validation

2. **Gemini provider schema**
   - same object/array/type/enum structure
   - same required fields and nullable unions
   - documented Gemini-compatible constraints
   - unsupported local-only keywords removed

The result from Gemini is validated again against the original Pydantic model.
Provider schema sanitization therefore does not weaken Tia's write safety.

## No fallback architecture

This fix does not use:

- keyword parsing
- function-calling-as-schema
- free-form JSON repair
- regex intent detection

The path stays:

semantic Gemini extraction
→ native JSON Schema structured output
→ full Pydantic validation
→ deterministic onboarding validation
→ explicit Admin confirmation
→ PostgreSQL transaction

## Error boundary

`ChatGoogleGenerativeAI` wraps Google SDK `ClientError` exceptions. v0.16.2
unwraps the exception chain to recover the HTTP status and converts provider
failures into Tia's normal `LLMProviderError`, preventing opaque FastAPI 500s.
