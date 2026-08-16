# Tia v0.16.5 — Onboarding structured-output budget

## Observed failure

Gemini accepted the compact onboarding JSON Schema and returned a valid
object, but the object stopped after `branch_hours`. Fields that occur
later in the provider schema were absent and local Pydantic validation
correctly rejected the partial result.

The onboarding model was still using Tia's global 2048-token output
budget. The realistic onboarding scenario also expanded "every day" into
fourteen branch-hour rows before the model reached doctor relationships
and booking settings.

## Fix

- AI onboarding now has its own 8192-token output budget.
- Customer-agent/router/flow budgets are unchanged.
- Provider schedule rules use a compact `weekdays` array.
- `weekdays=[0,1,2,3,4,5,6]` is expanded by Python into seven domain
  working-hour rows after extraction.
- All provider top-level fields remain required. Partial output still
  fails closed; Tia never silently treats missing doctor/service links or
  booking settings as empty.
- Gemini thinking remains `medium`; quality was not traded away to solve
  an output-size problem.

## Resulting path

Gemini compact weekly plan
-> full required provider DTO
-> Python weekday expansion
-> full domain Pydantic validation
-> deterministic relationship validation
-> explicit Admin confirmation
-> atomic PostgreSQL execution
