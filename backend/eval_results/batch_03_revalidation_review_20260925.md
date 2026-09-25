# Batch 3 Revalidation Review

- Frozen baseline: `ed8e263ff504625b15cc04c40f16a288905dd20a`
- Model: `gpt-5.6-luna`
- Reasoning effort: `low`
- Workspace: Demo `tia`
- Scenario version: `batch3-v1`
- Fixture version: `batch3-demo-fixtures-v1`
- Review date: 2026-09-25
- Product runtime changes during revalidation: none

## Focused gate

Scenarios: S1, S4, S5, S6, S7, S8, S9, S15.

Result: 8/8 PASS after manual review. There were no deterministic P0/P1/P2
findings and no infrastructure failures.

Focused usage:
- Turns: 17
- LLM calls: 32
- Input tokens: 141,747
- Cached-read tokens: 80,295
- Cache-write tokens: 33,515
- Uncached input tokens: 27,937
- Output tokens: 5,406
- Total tokens: 147,153
- LLM latency: 97,958 ms
- Retries: 0
- Fallback calls: 0
- Actual cost: $0.02205925

Focused findings:
- S1 correctly routed the outstanding-balance question to Reception with
  `financial_ownership=reception`, no financial reads, and no financial write.
- S4/S5/S6/S15 kept source-appointment identity separate from replacement
  date/time and changed only the intended appointment.
- S7 clarified verified appointment ambiguity without a write.
- S8 bound `التاني` to candidate #2 and wrote only on the later reschedule turn.
- S9 bound `التاني` to candidate #2 and cancelled only after explicit confirmation.

## RC1-RC7 deterministic controls

Existing control suite result: **117 passed**.

No Batch 2 live rerun was performed.

## Full Batch 3

All 22 scenarios ran on the same frozen baseline.

Usage:
- Turns: 47
- LLM calls: 89
- Interpreter calls: 45
- Responder calls: 44
- Input tokens: 389,117
- Cached-read tokens: 240,885
- Cache-write tokens: 73,116
- Uncached input tokens: 75,116
- Output tokens: 16,024
- Total tokens: 405,141
- Interpreter latency: 158,701 ms
- Responder latency: 83,119 ms
- Total LLM latency: 241,820 ms
- Turn latency: 274,805 ms
- Retries: 0
- Fallback calls: 0
- Infrastructure failures: 0
- Actual cost: $0.05734870

Manual classification:
- Fully Correct: 19
- Acceptable / Minor: 3
- Failed: 0
- Product P0: 0
- Product P1: 0
- Product P2: 0
- Product P3: 2
- Evaluator false positives: 1

## Scenario review

| Scenario | Classification | Severity / note |
| --- | --- | --- |
| S1 | Fully Correct | Financial ownership boundary correct |
| S2 | Fully Correct | Staff takeover/handback correct |
| S3 | Fully Correct | Financial handoff then fresh booking correct |
| S4 | Fully Correct | Human-owned lifecycle request suppressed; handback correct |
| S5 | Fully Correct | Source/replacement binding correct |
| S6 | Fully Correct | Same-service source binding correct |
| S7 | Fully Correct | Ambiguity clarified; no write |
| S8 | Acceptable / Minor | P3: candidate #2 was bound correctly, but the response redundantly asked the user to reconfirm its date |
| S9 | Fully Correct | Selected second appointment cancelled only after confirmation |
| S10 | Fully Correct | Last package session reserved exactly once |
| S11 | Fully Correct | Exhausted package blocked without fallback booking |
| S12 | Fully Correct | Expired package blocked without mutation |
| S13 | Fully Correct | Deterministic eligible-package selection correct |
| S14 | Acceptable / Minor | Evaluator false positive; runtime correctly handed off cancellation inside the notice window |
| S15 | Fully Correct | Package reservation transferred on reschedule |
| S16 | Fully Correct | Old cancelled workflow did not leak |
| S17 | Fully Correct | Stale doctor preference did not leak |
| S18 | Fully Correct | Stale device did not leak |
| S19 | Fully Correct | Price/package grounding and booking correct; no payment/Pulse mutation |
| S20 | Fully Correct | Side price query preserved reschedule continuity |
| S21 | Acceptable / Minor | P3: DB booking was correct, but final response did not acknowledge the successful booking |
| S22 | Fully Correct | Abandoned laser task cleared before fresh Hydrafacial booking |

### S14 evaluator false positive

S14's cancellation step produced a Reception handoff, left the appointment confirmed,
and kept the package reservation intact. This is the safe policy outcome when the
appointment is inside the configured cancellation notice window. The scenario fixture
uses the generic earliest-bookable-slot helper and does not guarantee an appointment
outside that window. The existing Batch 1 cancellation evaluation has a dedicated
safe-cancellation fixture that explicitly selects outside the notice window.

Therefore S14 did not demonstrate a package lifecycle product failure. Its deterministic
expectation was not applicable to the time-relative fixture selected for this run.

## Verdict

There are no unresolved product P0/P1 findings, no wrong writes, no financial-boundary
regression, and no lifecycle corruption in the reviewed run.

**BATCH 3 CLOSED**
