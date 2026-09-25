# Tia Agent Evaluation — Batch 4 Reviewed Baseline

- Frozen runtime baseline: `644e58feeacc4a4f540b6e5460bc35c7676487af`
- Evaluation harness SHA: `172b45331347a6592dccc626e7b9031ac1ba5a6f`
- Model: `gpt-5.6-luna`
- Reasoning effort: `low`
- Workspace: Demo `tia`
- Scenario version: `batch4-v1`
- Fixture version: `batch4-demo-fixtures-v1`
- Official run: `batch_04_raw_20260925T203936Z.json`
- Product runtime changes during evaluation: none

## Validation and controls

- Batch 4 + unified-runner unit tests: 13 passed locally.
- Full eval tooling tests on `tia-agent-eval`: 35 passed.
- Ruff: PASS.
- Compileall: PASS locally.
- `git diff --check`: PASS.
- RC1–RC7 / Batch 3 focused deterministic regression controls: 117 passed.
- Canonical V2 cancellation-policy controls: 5 passed.
- Official live run infrastructure failures: 0.
- No Batch 2 or Batch 3 full live rerun was performed.

The official run used the existing Demo guard, PostgreSQL advisory transaction lock,
savepoint-bound Session, and per-scenario outer transaction rollback. Scenario DB deltas
were reviewed from in-transaction evidence; no persistent write path was intentionally
used by the harness.

## Official run metrics

- Scenarios: 17
- Customer turns: 38
- LLM calls: 70
- Interpreter calls: 35
- Responder calls: 35
- Input tokens: 288,506
- Cached-read tokens: 187,355
- Cache-write tokens: 58,878
- Uncached input tokens: 42,273
- Output tokens: 13,197
- Total tokens: 301,703
- Interpreter latency: 125,078 ms
- Responder latency: 60,650 ms
- Total LLM latency: 185,728 ms
- Turn latency: 210,725 ms
- Retries: 0
- Fallback calls: 0
- Actual cost: $0.04275760
- Cost without explicit cache: $0.07353760
- Cache saving: 41.86%

## Manual classification

- Fully Correct: 11
- Acceptable / Minor: 1
- Failed: 5
- Product P0: 0
- Product P1: 2
- Product P2: 3
- Product P3: 1
- Evaluator false positives: 1 deterministic P1 classification in S10; the scenario still contains a genuine P2 product issue
- Official infrastructure failures: 0

## Scenario review

| Scenario | Classification | Severity / note |
| --- | --- | --- |
| S1 | Fully Correct | Five-day-gap booking resolved canonically and only the intended appointment was rescheduled |
| S2 | Fully Correct | Long-gap cancellation resolved the single actionable upcoming appointment |
| S3 | Acceptable / Minor | P3: completed appointment stayed non-actionable, but the reply asked which booking instead of saying no actionable upcoming booking was found |
| S4 | Fully Correct | Financial handoff, handback and four-day-gap fresh booking remained clean; no payment/Pulse mutation |
| S5 | Fully Correct | After Reception changed the appointment, the Agent read the new canonical DB truth |
| S6 | Failed | P2: human-owned messages were silent/no-write, but their stale reschedule semantics leaked into the first post-handback turn |
| S7 | Failed | P1: package-backed cancellation after reschedule executed directly instead of handing off before entitlement mutation |
| S8 | Fully Correct | Package covered PRP only; Hydrafacial remained standard; no invented coverage or financial settlement |
| S9 | Fully Correct | Canonical exhausted package state won over stale conversation history |
| S10 | Failed | P2: broad “laser” target was lost before appointment resolution, causing an unscoped availability path and no modification |
| S11 | Fully Correct | Cancel A then modify B preserved the remaining appointment scope |
| S12 | Fully Correct | Same service/date/device disambiguation selected Prime Lase deterministically and left Candela untouched |
| S13 | Failed | P1: safe package-info response exposed customer balance-due ledger truth even though no financial-ledger question was asked |
| S14 | Fully Correct | Changing service invalidated Hydrafacial availability and revalidated PRP before any booking |
| S15 | Fully Correct | Incremental date/doctor/service corrections ended in exactly the latest explicit Hydrafacial state |
| S16 | Failed | P2: repeat reschedule confirmation did not write again, but was treated as a fresh reschedule/availability flow instead of acknowledgment |
| S17 | Fully Correct | Repeat package booking confirmation produced no duplicate appointment or PackageUsage |

## Family summary

- Multi-day lifecycle: PASS, with one P3 response-quality note in S3.
- Handoff across time: FAIL — S6.
- Package lifecycle: FAIL — S7.
- Concurrent appointments: FAIL — S10.
- Multi-intent: FAIL — S13.
- Idempotency: FAIL — S16.

## Findings

### S6 — Human-owned messages leak into post-handback semantics

**Severity:** P2

**Root cause:** The conversation history loader reads patient, AI and staff messages without
an ownership-epoch boundary. Messages received while Reception owns the chat therefore
remain in the native recent dialogue seen by the interpreter after handback. In this run,
the fresh question “جلسة الهيدرافيشل بكام؟” correctly received a price-only visible reply,
but structured understanding also replayed the earlier human-owned reschedule constraints
(Friday / after noon), triggering unnecessary appointment and availability reads.

**Evidence:**
- Three inbound turns while human-owned: AI reply = none, write = false.
- First post-handback turn: visible answer was only the Hydrafacial price.
- Structured operations on that same turn included stale `reschedule` plus the new `pricing` operation.
- DB delta contained no appointment mutation.

**Option A:** Filter AI semantic history by ownership epoch so customer messages handled
during a human-owned interval are not replayed after handback.

**Option B:** Mark human-owned inbound messages as staff-handled and exclude those messages
from later interpreter continuity.

**Option C:** Reset conversational semantic continuity at handback and provide a minimal
staff-authored handback summary when continuity is intentionally needed.

**Recommended solution:** Option A, with a deterministic ownership-epoch boundary. It is the
smallest source-of-truth fix and preserves canonical DB state independently of chat history.

### S7 — Package-backed cancellation bypasses financial ownership policy

**Severity:** P1

**Root cause:** The live V2 orchestrator advances read-backed writes through
`advance_step_after_verification` directly. The central financial cancellation guard lives
in `advance_step_with_write_policies`, so that guard is not applied on this live path.
The lower-level cancellation notice rule can still cause handoff for appointments inside
the notice window, which masked this gap in an earlier Batch 3 case. Here the rescheduled
package-backed appointment was outside that masking condition, so cancellation executed.

**Evidence:**
- Booking used the package, then reschedule preserved `package_prepaid` and the same reservation.
- Cancellation turn read the exact appointment and returned `write_result=completed`.
- Final appointment was cancelled; PackageUsage became `released`; package remaining restored exactly once.
- The target row still carried `patient_package_id`, `billing_context=package_prepaid`, and `payment_status=paid`.
- Frozen-runtime cancellation-policy tests: 5/5 PASS and explicitly require package-backed cancellation to hand off before write.

**Option A:** Route the live orchestrator’s post-read advancement through the existing
`advance_step_with_write_policies` function.

**Option B:** Add the same financial-effect guard to the write executor as a defensive final gate.

**Option C:** Force package-backed cancellation to handoff earlier in planner/state logic.

**Recommended solution:** Option A, reusing the existing central deterministic policy instead
of duplicating rules. Option B can later be considered defense-in-depth, not the primary fix.

### S10 — Broad service category is lost during concurrent lifecycle resolution

**Severity:** P2

**Root cause:** The user clearly scoped the lifecycle request to “الليزر”, but structured
`source_appointment` contained no service/category information. The planner consequently
read both upcoming appointments and performed replacement availability without a verified
source appointment/service. It returned an appointment-choice outcome instead of modifying
the one laser appointment.

The raw deterministic guard labeled this as P1 “changed the wrong appointment or package”.
That label is a false positive: no write occurred and no appointment/package changed.
Manual severity is P2 because target resolution was lost safely.

**Evidence:**
- Verified appointments contained exactly one laser appointment and one Hydrafacial appointment.
- `source_appointment` was empty in structured understanding.
- Availability read carried only replacement date/time with `reschedule=true`.
- Outcome asked for appointment choice; DB delta was empty.
- Skin appointment and unrelated package were untouched.

**Option A:** Add a typed broad source-category signal (for example laser) to lifecycle interpretation.

**Option B:** Resolve broad source categories against verified current appointments using
canonical service metadata (for laser, service/device metadata), then run availability only
after one source appointment is selected.

**Option C:** If broad-category resolution cannot deterministically produce one current
appointment, clarify before any availability read.

**Recommended solution:** Option B, with the category represented semantically rather than
keyword/regex routing. Appointment-first verified resolution should precede replacement availability.

### S13 — Package information exposes receptionist-owned ledger truth

**Severity:** P1

**Root cause:** The normal `customer_packages` read currently calls
`list_patient_packages(..., include_financials=True)`. The customer-visible projection
removes IDs but converts every `*_minor` field, including `balance_due_minor`, into a
visible money fact. The responder therefore received and verbalized the outstanding package
balance during a price/package-eligibility/availability question.

**Evidence:**
- User asked service price, package eligibility and availability only.
- Structured operations were `pricing`, `package_info`, and `availability`, all with `financial_ownership=none`.
- Verified reads: `service_catalog`, `customer_packages`, `availability`.
- Reply added “الرصيد المستحق عليها 6000 جنيه”.
- No payment, Pulse, appointment or package mutation occurred.

**Option A:** For ordinary package-info reads, use `include_financials=False`; receptionist-owned
ledger facts should not enter the Agent-owned read bundle.

**Option B:** Add a customer-visible package projection allowlist that suppresses paid/refunded/balance-due
fields regardless of internal read contents.

**Option C:** Add responder-only instructions to ignore ledger fields unless separately authorized.

**Recommended solution:** Option A plus an output allowlist as defense-in-depth. The ownership
boundary should be enforced before the responder sees the data, not by prompt compliance alone.

### S16 — Successful reschedule confirmation is not normalized to acknowledgment

**Severity:** P2

**Root cause:** Recent-action acknowledgment normalization recognizes repeated booking and
bare repeated cancellation, but completed reschedule is not represented by
`_completed_action_context` and has no corresponding “same recent reschedule” normalization.
The second turn therefore re-entered reschedule planning.

**Evidence:**
- First turn successfully rescheduled Hydrafacial once.
- Follow-up “تمام كده خليها على الميعاد الجديد” performed no second write.
- It nevertheless re-read appointments/availability and replied with alternative doctors,
rather than acknowledging the already completed new appointment.
- DB contained exactly one replacement appointment.

**Option A:** Extend completed-action context and recent-action acknowledgment normalization
to successful reschedules.

**Option B:** Introduce a generic recently-completed lifecycle action key used by booking,
cancel and reschedule idempotency checks.

**Option C:** Handle the phrase only in the responder prompt while keeping planner behavior unchanged.

**Recommended solution:** Option A. It is the smallest symmetric extension of the existing
booking/cancellation acknowledgment mechanism and keeps idempotency deterministic.

### S3 — Completed appointment response finish

**Severity:** P3

**Root cause:** The canonical appointment read correctly returned no actionable completed
appointment, but the no-match lifecycle outcome used a generic clarification response.

**Evidence:** No write; completed appointment stayed completed; DB delta was empty.

**Option A:** Use a specific “no actionable upcoming appointment found” response for zero verified lifecycle targets.

**Option B:** Add a dedicated no-actionable-appointment outcome.

**Option C:** Keep the generic clarification.

**Recommended solution:** Option A if response polish is addressed with the other findings.

## Verdict

There are no P0 findings and no persistent-write safety incident in the reviewed evidence,
but Batch 4 exposed two unresolved P1 product issues:
1. package-backed cancellation can bypass the financial ownership handoff; and
2. safe package information can expose customer ledger balance truth.

It also exposed three material safe P2 continuity/idempotency failures.

**BATCH 4 NOT CLOSED**
