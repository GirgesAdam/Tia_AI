# Tia Agent Evaluation — Batch 03 Reviewed Baseline

Date: 2026-09-25

## Verdict

**BATCH 3 NOT CLOSED**

The official reviewed baseline contains **14 Fully Correct**, **1 Acceptable/Minor**, and **7 Failed** scenarios. Manual severity is **P0=0, P1=7, P2=1, P3=0**.

No P0 was observed, but seven P1 product failures remain, so Batch 3 cannot close on this baseline.

## Frozen run identity

- BATCH3_BASE_SHA: 64fc422ebb9b35e0df12fcd260bc1986c9cf1032
- Harness SHA: d1f9f3ff022f31527671a223e92563d12f4e2e2e
- Scenario version: batch3-v1
- Fixture version: batch3-demo-fixtures-v1
- Workspace: tia (Demo-only guard enabled)
- Model: gpt-5.6-luna
- Fallback model: gpt-5-mini
- Reasoning effort: low
- Generated at: 2026-09-25T10:19:42.852895+00:00
- origin/main reconciliation at review close: unchanged at the same BATCH3_BASE_SHA
- Runtime diff between frozen base and harness branch: none under backend/app

## Execution and regression gates

- Harness tests: **22/22 passed**
- RC1–RC7 deterministic controls: **117/117 passed**
- Live scenarios: **22**
- Customer turns: **47**
- LLM calls: **88** = interpreter 45 + responder 43
- Infrastructure failures in this official run: **0**
- Provider retries: **0**
- Fallback calls: **0**

The deterministic regression suite is green, but Batch 3 exposed a meaningful **RC2 contextual regression/gap**: an outstanding-balance question inside an active booking can be misclassified as service pricing rather than a Reception-owned financial-ledger concern.

## Token and cost accounting

| Metric | Value |
| --- | ---: |
| Input tokens | 343,448 |
| Output tokens | 15,366 |
| Total tokens | 358,814 |
| Cached-read tokens | 196,245 |
| Cache-write tokens | 70,562 |
| Uncached input tokens | 76,641 |
| Average tokens/scenario | 16,309.73 |
| Median tokens/scenario | 10,599.00 |
| Max tokens | 56,118 (b3_21_repeated_corrections) |
| Provider latency, all calls | 240,938 ms |
| Actual modeled cost | USD 0.05533280 |
| No-explicit-cache equivalent | USD 0.08712880 |
| Cache saving | USD 0.03179600 (36.49%) |

Pricing inputs were explicitly supplied from the official OpenAI GPT-5.6 Luna pricing checked on 2026-09-25: input USD 0.20/M, cached input USD 0.02/M, output USD 1.20/M, explicit cache-write multiplier 1.25× input.

## Manual scenario review

| Scenario | Category | Verdict | Severity | Tokens | Cost | Manual finding |
| --- | --- | --- | --- | ---: | ---: | --- |
| b3_01_handoff_during_active_booking | handoff_handback | FAILED | P1 | 35,263 | USD 0.005902 | Outstanding-balance question inside an active booking was interpreted as service pricing (650 EGP) instead of a Reception-owned financial-ledger concern. Booking state survived and no financial write occurred, but the answer was materially wrong and no handoff was created. |
| b3_02_staff_takeover_then_handback | handoff_handback | FULLY_CORRECT | — | 21,698 | USD 0.003826 | Agent stayed silent with zero LLM/write activity while Reception owned the conversation; ownership epoch changed on takeover/handback; no staff reply replayed. |
| b3_03_financial_handoff_then_new_booking | handoff_handback | FULLY_CORRECT | — | 13,714 | USD 0.001849 | Financial balance question handed to Reception with no financial read/write; after explicit staff handback, a new Hydrafacial booking completed correctly. |
| b3_04_lifecycle_while_human_owns | handoff_handback | FAILED | P1 | 13,510 | USD 0.001837 | Human-ownership suppression worked correctly. After handback, the new destination date/time were reused to search for the source appointment, yielding zero appointment matches and blocking a valid reschedule. |
| b3_05_two_appointments_explicit_date | multi_appointment | FAILED | P1 | 6,727 | USD 0.000864 | The source appointment date stated by the customer was not preserved as a source selector; the planner used the replacement date/time for the appointments read, so the intended appointment was not resolved and no reschedule occurred. |
| b3_06_two_same_service_explicit_date | multi_appointment | FAILED | P1 | 6,755 | USD 0.000894 | Same-service disambiguation failed for the same reason: destination date/time filtered the source-appointment read instead of selecting the existing appointment by its current date. |
| b3_07_real_appointment_ambiguity | multi_appointment | ACCEPTABLE_MINOR | P2 | 6,857 | USD 0.000979 | The Agent failed closed with no write, but asked the customer to choose from the entire laser service catalog before reading the two actual matching appointments. Safe, but unnecessarily broad and less natural than appointment-first clarification. |
| b3_08_candidate_selection_followup | multi_appointment | FAILED | P1 | 22,447 | USD 0.003790 | The verified second appointment was identified, but the ordinal follow-up immediately executed a no-op reschedule to the appointment's existing time before a replacement time was supplied. A later real replacement request then lost the verified device and asked again. This is an incorrect lifecycle mutation even though it stayed on the selected appointment. |
| b3_09_cancel_one_of_multiple | multi_appointment | FAILED | P1 | 20,675 | USD 0.002898 | Generic 'laser' ambiguity was resolved against the service catalog, so 'the second' bound to the second service candidate rather than the second current appointment. Cancellation never executed; no wrong appointment was cancelled. |
| b3_10_one_session_remaining | package_lifecycle | FULLY_CORRECT | — | 6,957 | USD 0.000947 | Exactly one package-backed appointment and one reserved PackageUsage were created; remaining sessions moved 1→0 once. |
| b3_11_exhausted_package | package_lifecycle | FULLY_CORRECT | — | 7,001 | USD 0.000968 | Explicit package booking was safely blocked with zero appointment/usage creation when entitlement was exhausted. |
| b3_12_expired_package | package_lifecycle | FULLY_CORRECT | — | 7,009 | USD 0.000978 | Expired package with positive recorded sessions was correctly rejected; no entitlement or appointment mutation. |
| b3_13_two_eligible_packages | package_lifecycle | FULLY_CORRECT | — | 6,960 | USD 0.000945 | Current deterministic domain policy selected the earlier-expiring eligible package; the other package remained untouched. |
| b3_14_package_booking_then_cancel | package_lifecycle | FULLY_CORRECT | — | 14,176 | USD 0.002002 | Package reservation was created once, then released once on cancellation; remaining entitlement returned to its original value. |
| b3_15_package_booking_then_reschedule | package_lifecycle | FAILED | P1 | 14,004 | USD 0.001971 | Initial package booking was correct and package state stayed safe, but the replacement date/time were used for source appointment lookup, so the package-backed appointment could not be rescheduled. No duplicate/released usage corruption occurred. |
| b3_16_old_cancelled_workflow_isolation | returning_customer_isolation | FULLY_CORRECT | — | 7,135 | USD 0.001057 | Fresh Hydrafacial booking ignored an old cancelled laser workflow; historical cancellation remained inert. |
| b3_17_old_doctor_preference_isolation | returning_customer_isolation | FULLY_CORRECT | — | 7,160 | USD 0.001089 | Explicit current doctor overrode stale doctor history and the canonical appointment used the requested doctor. |
| b3_18_old_device_isolation | returning_customer_isolation | FULLY_CORRECT | — | 7,243 | USD 0.001166 | Explicit Candela choice overrode stale Prime Lase history; canonical booking stored Candela. |
| b3_19_price_package_booking | complex_multi_intent | FULLY_CORRECT | — | 7,688 | USD 0.001529 | Price, package eligibility, remaining sessions, and booking were grounded correctly; package usage was reserved and no Pulse/payment ledger mutation occurred. |
| b3_20_side_query_during_reschedule | complex_multi_intent | FULLY_CORRECT | — | 26,834 | USD 0.003507 | Read-only price side query did not destroy the active reschedule target; the original appointment was later rescheduled correctly. |
| b3_21_repeated_corrections | complex_multi_intent | FULLY_CORRECT | — | 56,118 | USD 0.009791 | Repeated corrections converged on the final PRP-hair service, doctor, date, and time with one booking and no stale write. |
| b3_22_abandon_then_different_booking | complex_multi_intent | FULLY_CORRECT | — | 42,883 | USD 0.006542 | Abandoned laser task was cleared; fresh Hydrafacial booking contained no stale laser/device constraints. |

## Product-boundary conclusions

**Financial/Pulse boundary:** no scenario produced a Pulse balance mutation, Pulse settlement, or payment-ledger mutation outside its allowed business domain. S1 is nevertheless a P1 semantic ownership failure because an outstanding-balance question was answered with the current session price instead of being handed to Reception.

**Human ownership:** S2 proves the runtime suppresses Agent work while owner_type=human; the human-owned turn produced no Agent response, no LLM calls, and no write. The ownership epoch changed at takeover and handback, and the staff response was not replayed. S4 also stayed silent while human-owned; its failure happens only after handback during reschedule target resolution.

**Session packages:** S10–S14 pass the critical entitlement invariants: last-session reservation exactly once, exhausted/expired fail closed, deterministic selection across two eligible packages, and exact release on cancellation. S15 preserves package safety but cannot complete reschedule because source appointment resolution is broken.

**Returning-customer isolation:** S16–S18 all pass. Old cancelled state, doctor preference, and device context do not override explicit current requests.

**Complex conversational continuity:** S19–S22 pass. Price+package+booking stays grounded; side queries preserve an active reschedule target; repeated corrections converge on latest explicit values; explicit abandonment clears the old task. S21 remains the most token-expensive scenario and should be a future optimization target, not a correctness blocker.

## Failure clusters

### F1 — Financial ownership intent collapses into active-service pricing (S1, P1)

The interpreter classified “فاضل عليا كام فلوس؟” inside an active laser booking as pricing and inherited the active service/device, producing a verified service-catalog price of 650 EGP. No human_support operation or financial-ledger semantic marker was emitted.

This is a contextual gap in RC2: the simple financial-handoff behavior is protected by tests, but active booking context can still steer a ledger question into pricing.

### F2 — Reschedule source appointment and replacement constraints share one parameter bag (S4, S5, S6, S15, P1)

planner._base_parameters() places operation date/time in the same params object used for both the source appointments read and replacement availability read. In the reschedule path, the planner emits appointments(parameters=params) and availability(parameters={**params, "reschedule": True}).

The read executor then filters current appointments by params["date"]. When that date is the requested new date, the source appointment disappears from the verified read (visit_count=0) and the write blocks.

The business write layer is not the root cause; it correctly refuses to mutate without one verified source appointment.

### F3 — Lifecycle choice scope is not consistently appointment-first (S7 P2, S8/S9 P1)

For lifecycle requests, generic “laser” can be expanded into the service catalog before current appointments are read. S9 therefore binds “التاني” to the second service candidate rather than the second appointment. S7 fails safely but asks an unnecessarily broad service question.

S8 shows a related state problem from the opposite direction: the runtime presents two verified appointment choices, but the choice is not persisted as a durable lifecycle target. “التاني” is reconstructed as a complete reschedule using the selected appointment’s own current date/time, causing an immediate no-op reschedule write. The later actual replacement request then has no persisted source appointment/device and re-enters ambiguous planning.

## RC1–RC7 regression statement

- RC1: deterministic controls green; no package-vs-overage conflation observed.
- RC2: **contextual regression/gap exposed by S1**. Financial DB safety held, but the semantic ownership decision was wrong inside an active booking.
- RC3: deterministic controls green; package/Pulse lifecycle safety was not regressed by Batch 3.
- RC4: correction/side-query/abandonment scenarios S20–S22 pass; lifecycle candidate persistence still has a separate Batch 3 gap in S8.
- RC5: deterministic controls green; no conditional fallback regression observed.
- RC6: deterministic controls green; no doctor-comparison regression observed.
- RC7: deterministic controls green; no duplicate/already-completed conversational acknowledgment regression observed.

## Evaluation/tooling notes

Earlier attempts that failed before or outside the official baseline were classified as evaluator infrastructure only: Ruff cache permissions in the eval container, missing backend/tests in the eval image, an evaluator helper that raised when a handoff was absent, and Railway stdout truncation for the very large Base64 payload. They did not count as Agent failures. The official reviewed run above has zero infrastructure failures.

A prior evaluator false positive for Arabic-digit price rendering was fixed in the evaluator before this official run; it does not appear in the reviewed results.

## Required next task

Do not patch these failures in this baseline branch. A separate runtime-fix task should address F1 and the lifecycle resolver (F2/F3), then re-run at minimum S1, S4–S9, S15, RC1–RC7 deterministic controls, and finally all 22 Batch 3 scenarios.

See docs/AGENT_EVAL_BATCH_03_ROOT_CAUSES_20260925.md for solution options.
