# v0.16.3 — Compact Gemini onboarding provider schema

The AI onboarding domain model is intentionally rich because it represents
clinic configuration and relationships. That model is no longer sent directly
to Gemini.

Gemini now receives `OnboardingProviderDecision`, a flat relational transport
DTO:

- `branches`
- `services`
- `doctors`
- `branch_hours`
- `doctor_branches`
- `doctor_services`
- `doctor_hours`
- `booking_settings`

Python then converts the provider DTO into Tia's authoritative
`OnboardingPlan`.

This has three benefits:

1. Lower structured-output nesting/complexity.
2. Provider schema is independent from database/domain evolution.
3. All existing local Pydantic and deterministic business validation remains
   authoritative.

Before sending the provider DTO schema to Gemini, Tia canonicalizes Pydantic
JSON Schema:

- local `$defs/$ref` are inlined;
- nullable `anyOf` becomes `type: [T, "null"]`;
- local-only constraints are omitted from the provider copy;
- the original Pydantic model validates the result again.

General `anyOf` unions and recursive refs fail locally rather than being sent
as an opaque Gemini request.

No regex parsing, intent keywords, free-form JSON repair, or function-call
schema fallback was added.
