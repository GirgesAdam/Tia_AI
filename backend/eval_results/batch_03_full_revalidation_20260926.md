# Tia AI — Batch 3 Full Revalidation on Latest Main

## Task

Batch 3 Full Revalidation

- Starting main SHA: `0c71edb00d03efdcd260bcc4b58dd428a398e865`
- Final tested SHA: `0c71edb00d03efdcd260bcc4b58dd428a398e865`
- Branch: `eval/batch3-full-revalidation`
- Batch 3 fixes included: **YES**
- Alembic head: `0086_all_service_packages`
- Runtime behavior changes during this task: **NONE**
- Production deployment: **NOT REQUIRED / NOT PERFORMED**

## Environment / preflight

- Workspace: Demo `tia`
- Canonical seed: `demo-canonical-2026-09-17-v1`
- Batch fixture version: `batch3-demo-fixtures-v1`
- Active branches: 1 (`Tia Clinic`)
- Services: 48 total / 29 active / 19 inactive
- Doctors: 23
- Canonical service preflight: **PASS**
- External dispatch: **blocked**
- LLM provider: OpenAI
- Model: `gpt-5.6-luna`
- Reasoning effort: `low`
- Database connection: **PASS**
- Demo guard: **PASS**
- PostgreSQL advisory lock: **ENABLED**
- Per-scenario outer transaction rollback: **ENABLED**
- Session savepoint mode: `create_savepoint`

The canonical preflight reported no duplicate active services, no invalid pricing rows,
no missing required services, and no seed mismatch. No reseed was performed.

## Batch 3 fixes present

Verified as ancestors of the tested SHA:

- F1 / financial ownership focused fixes: included.
- F2 / appointment lifecycle fixes: included.
- RC7 grounded acknowledgment fix: included.
- S7 package-backed cancellation policy fix: included.
- S13 customer-package financial exposure fix: included.

## Full run

Official artifact:

- `backend/eval_results/batch_03_raw_20260925T225438Z.json`
- `backend/eval_results/batch_03_raw_20260925T225438Z.md`

All 22 Batch 3 scenarios executed. No scenario had an execution/infrastructure error.

| Classification | Count |
| --- | ---: |
| PASS | 21 |
| BEHAVIOR_REVIEW_REQUIRED | 1 |
| DETERMINISTIC_FAILURE | 0 |
| EVAL_INFRA_FAILURE | 0 |

The harness emitted one deterministic P1 guard in S14. Manual review and two
independent reproductions show it is the same known evaluator false positive from the
previous Batch 3 baseline: the package-backed appointment is intentionally handed off
instead of cancelled by the Agent. The appointment remains confirmed and the package
reservation remains reserved. This is the current fail-closed financial-ownership policy,
not a product lifecycle corruption.

## Scenario results

| Scenario | Result | Notes |
| --- | --- | --- |
| S1 | PASS | Financial question handed to Reception; no financial read/write; booking task preserved. |
| S2 | PASS | Staff takeover/handback preserved task ownership correctly. |
| S3 | PASS | Financial handoff followed by fresh booking; booking write isolated from financial handoff. |
| S4 | PASS | Lifecycle request suppressed while human owned conversation; handback resumed safely. |
| S5 | PASS | Correct source appointment rescheduled; no wrong replacement. |
| S6 | PASS | Same-service source appointment bound correctly. |
| S7 | PASS | Real appointment ambiguity clarified; no write. |
| S8 | BEHAVIOR_REVIEW_REQUIRED | Candidate #2 bound correctly and only intended appointment changed. Official run redundantly reconfirmed the selected appointment. Two extra reproductions showed response variance: one clean, one produced a weak final availability-style response despite deterministic DB success. No wrong write was observed. P3 responder/conversational quality only. |
| S9 | PASS | `التاني` bound to second appointment; cancellation occurred only after confirmation. |
| S10 | PASS | Last package session reserved exactly once. |
| S11 | PASS | Exhausted package blocked; no fallback booking. |
| S12 | PASS | Expired package blocked; no mutation. |
| S13 | PASS | Deterministic eligible-package selection correct. |
| S14 | PASS | Harness P1 is evaluator false positive. Package-backed cancellation correctly failed closed to human handoff; reproduced twice. |
| S15 | PASS | Package reservation transferred correctly during reschedule. |
| S16 | PASS | Old cancelled workflow did not leak. |
| S17 | PASS | Historical doctor preference did not override explicit doctor. |
| S18 | PASS | Historical device did not override explicit device. |
| S19 | PASS | Price + package eligibility + booking grounded correctly; no payment/Pulse mutation. |
| S20 | PASS | Side price query preserved reschedule continuity. |
| S21 | PASS | Repeated corrections resolved to final PRP-hair/Hala booking and final response acknowledged success. Previous Batch 3 P3 acknowledgment issue is resolved in this run. |
| S22 | PASS | Abandoned laser task did not leak into fresh Hydrafacial booking. |

## Financial ownership

**PASS**

S1 financial query (`فاضل عليا كام فلوس؟`) produced a Reception handoff with:
- no financial ledger read,
- no invented balance,
- no financial write.

S19 package informational read remained available. A recursive inspection of the
customer-package turn evidence found none of these receptionist-owned ledger fields:
`sale_price_minor`, `amount_paid_minor`, `amount_refunded_minor`,
`balance_due_minor`, `purchase_transaction_id`,
`cancellation_default_charge_minor`,
`standalone_session_price_minor_at_purchase`.

## Appointment lifecycle

**PASS**

Reschedule/cancel/multiple-appointment/candidate-selection/package-backed flows did not
produce a wrong appointment mutation, duplicate replacement, or accidental cancellation.
S14 package-backed cancellation correctly failed closed to staff instead of mutating the
appointment/package reservation.

## Package safety

**PASS**

Package status/eligibility/session state remained usable by the Agent. Financial ledger
fields were not exposed in the inspected customer-package read evidence. Package booking,
exhaustion, expiry, deterministic package selection, and reschedule transfer behaved
consistently with the current policies.

## Handoff composition

**PASS**

Safe informational state survived human handoff where expected. Financial and
package-backed cancellation writes failed closed to human ownership. No unsafe
write-plus-handoff composition was observed.

## Database isolation

**PASS**

The Batch 3 runner uses, for every scenario:
1. Demo-only assertion,
2. PostgreSQL advisory lock,
3. outer transaction,
4. savepoint-bound SQLAlchemy Session,
5. unconditional outer rollback in `finally`.

In-scenario DB deltas were captured as evidence for intended writes. Persistent isolation
was additionally checked during the two S14 reproductions. After each reproduction the
global deltas were exactly zero for:

- appointments,
- payment_transactions,
- patient_packages,
- package_usages,
- patient_pulse_packs,
- pulse_usages,
- appointment_pulse_settlements.

No persistent evaluation write was found.

## S14 false-positive reproduction

Reproduced twice after the full run.

Both reproductions:
- had no execution error,
- emitted the same deterministic P1 evaluator guard,
- booked the package-backed appointment,
- handed cancellation to Reception,
- left persistent global DB deltas at zero after rollback.

Root cause classification: **evaluator expectation mismatch**, already documented in the
previous Batch 3 review. The fixture uses a time-relative appointment inside the current
financial/cancellation policy boundary; the evaluator still expects direct entitlement
restoration.

No runtime fix was made.

## P0 / P1 / P2 / P3

- P0: **0**
- Product P1: **0**
- Product P2: **0**
- Product P3: **1** — S8 conversational/responder variance only; appointment identity and DB mutation remained correct.
- Evaluator false positives: **1** — S14 deterministic P1 guard.
- Infrastructure failures inside scenarios: **0**

## Token usage / cost

Current run:

- Total scenarios: 22
- Total turns: 47
- Total LLM calls: 89
- Interpreter calls: 45
- Responder calls: 44
- Input tokens: 391,687
- Cached-read tokens: 235,532
- Cache-write tokens: 81,120
- Uncached input tokens: 75,035
- Output tokens: 15,667
- Total tokens: 407,354
- Retries: 0
- Fallback calls: 0
- Estimated/actual harness cost: **$0.05879804**
- No-cache equivalent: **$0.09713780**
- Cache saving: **39.47%**

Pricing used: GPT-5.6 Luna $0.20/M input, $0.02/M cached input,
$1.20/M output, cache writes at 1.25x uncached input.

### Previous Batch 3 baseline comparison

Previous reviewed full Batch 3:
- 22 scenarios / 47 turns / 89 LLM calls
- Input: 389,117
- Cached-read: 240,885
- Output: 16,024
- Total: 405,141
- Cost: $0.05734870

Latest main:
- Input: +2,570 (+0.66%)
- Cached-read: -5,353 (-2.22%)
- Output: -357 (-2.23%)
- Total: +2,213 (+0.55%)
- Cost: +$0.00144934 (+2.53%)
- LLM calls: unchanged
- Turns: unchanged

No material token/call-count regression was identified.

## RC1-RC7 controls

The deterministic regression union covering the RC fix files was rerun on latest main:
**147 passed**.

Additional Batch 3/Batch 4 focused safety controls:
**45 passed**.

Result:
- RC1: PASS
- RC2: PASS
- RC3: PASS
- RC4: PASS
- RC5: PASS
- RC6: PASS
- RC7: PASS

## CI / tooling validation

- Agent evaluation tooling tests: **35 passed**
- RC1-RC7 deterministic regression union: **147 passed**
- Batch 3/4 focused + orchestrator/package safety controls: **45 passed**
- Ruff: **PASS**
- compileall: **PASS**
- Alembic head: `0086_all_service_packages`
- `git diff --check`: PASS after cleanup

The full live runner completed all 22 scenarios and wrote both raw artifacts successfully.
After artifact generation, its final Windows console print hit a `cp1252`
`UnicodeEncodeError` while trying to emit Arabic compact evidence. This occurred after
the JSON/Markdown reports were written and does not affect scenario execution, token
metrics, DB rollback, or classification. It is recorded as non-blocking evaluation-tool
console noise; no tooling/runtime code was changed.

## Production deployment

**NOT REQUIRED**

No Railway or Vercel deployment was triggered by this task.

## Final assessment

Latest main is stable against the full Batch 3 scenario set for the requested safety
boundaries.

- Financial ownership: PASS
- Appointment lifecycle: PASS
- Package exposure: PASS
- Handoff composition: PASS
- DB isolation: PASS
- RC1-RC7: PASS
- Product P0/P1/P2 regressions: none
- Known/non-blocking P3: S8 conversational variance
- Evaluator false positive: S14

No Agent behavior, prompt, schema, planner, orchestrator, responder, business rule, Pulse
logic, financial ownership rule, or appointment lifecycle code was modified.
