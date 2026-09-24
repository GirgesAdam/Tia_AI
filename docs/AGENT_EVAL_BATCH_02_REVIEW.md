# Tia Agent Evaluation — Batch 02 Reviewed Baseline

Date: 2026-09-24

## Scope

Batch 02 evaluates the current Agent V2 runtime under realistic mixed, corrective,
Pulse-aware, and long-history conversations. This phase is evaluation-only: no runtime
fix is part of this report.

- Frozen runtime base SHA: `adebcf54aa9f152da10dab0f250f69d27f8e6223`
- Eval harness branch: `eval/agent-batch-02`
- Reviewed harness SHA: `e5e6a092605345930a218dd8f7832647d41c2558`
- Model: `gpt-5.6-luna`
- Reasoning effort: `low`
- Workspace: Demo only
- Scenario isolation: outer transaction rollback
- Concurrency isolation: PostgreSQL advisory transaction lock
- External side effects: blocked by Demo runtime policy

The local raw report used the frozen runtime SHA in its `git_sha` field. The runtime
under test is therefore unambiguous, while the durable harness SHA is recorded above.
The GitHub workflow records `GITHUB_SHA` separately for CI executions.
## Baseline execution

Final raw baseline:

- `batch_02_raw_20260924T104150Z.json`
- `batch_02_raw_20260924T104150Z.md`
- 24 scenarios
- 51 customer turns
- 100 LLM calls
- 0 infrastructure failures
- 0 deterministic P0 stops
- 1 provider retry
- 0 fallback-model calls
- 0 provider errors

Provider call split:

| Operation | Calls | Input | Output | Cached read | Cache write | Uncached | LLM latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| V2 interpreter | 52 | 279,985 | 13,076 | 217,516 | 0 | 62,469 | 185,010 ms |
| V2 responder | 48 | 71,735 | 3,325 | 0 | 71,591 | 144 | 85,273 ms |
| Total | 100 | 351,720 | 16,401 | 217,516 | 71,591 | 62,613 | 270,283 ms |

Token total: **368,121**.
## Cost accounting

Pricing used for the run was verified against OpenAI's current GPT-5.6 Luna pricing
on 2026-09-24:

- input: $0.20 / 1M tokens
- cached input: $0.02 / 1M tokens
- output: $1.20 / 1M tokens
- explicit cache writes: 1.25x normal input

Measured Batch 02 cost:

- actual: **$0.05445187**
- equivalent without explicit caching: **$0.09002520**
- saving: **$0.03557333**
- saving: **39.51%**

These figures use provider-reported token usage. They are not prompt-size estimates.

## Manual review summary

The deterministic checks are safety/grounding guards only. Final classification below
comes from manual transcript + structured trace + DB-state review.

- Fully correct: **12**
- Acceptable with minor issues: **8**
- Failed: **4**
- P0: **0**
- P1: **3**
- P2: **6**
- P3: **3**
- No issue: **12**
## Scenario review

| # | Scenario | Result | Severity | Reviewed finding |
| ---: | --- | --- | --- | --- |
| 1 | Compound price + booking | Fully correct | — | Canonical PRP price and booking intent both preserved; exact verified booking created after selection. |
| 2 | Two services in one turn | Fully correct | — | PRP-hair pricing and Candela underarm booking stayed in separate scopes. |
| 3 | Buy Pulse pack + book | Fully correct | — | +1000 Pulse entitlement, standard appointment billing, no payment/usage/settlement invented. |
| 4 | Explicitly ask to use Pulses | Fully correct | — | Booking remained standard; Pulse state unchanged; Reception settlement ownership explained. |
| 5 | Pulse balance + session package | Acceptable | P3 | Correct package-backed appointment and no Pulse mutation; reply adds unnecessary Pulse-settlement guidance. |
| 6 | Counted Pulse overage | Fully correct | — | Verified device-specific unit price and deterministic 1000-Pulse total. |
| 7 | Pulse pack offers + overage | Failed | P1 | Overage answered, but an existing pack offer disappeared from the read and reply. |
| 8 | Pulse financial ledger question | Failed | P2 | No invented amount/write, but receptionist-owned balance-due question was misclassified as owned-pack info. |
| 9 | Reschedule Pulse-billed appointment | Failed | P1 | Financial state stayed safe, but verified appointment/device context was lost and reschedule could not complete. |
| 10 | Cancel Pulse-billed appointment | Acceptable | P3 | First cancellation was correct/safe; redundant confirmation then reported no appointment instead of acknowledging prior cancellation. |
| 11 | Change service mid-flow | Acceptable | P2 | Latest service won safely, but previously supplied date was lost and requested again. |
| 12 | Change doctor mid-flow | Acceptable | P2 | Latest doctor won safely, but prior date was lost and requested again. |
| 13 | Change laser device mid-flow | Fully correct | — | Prime Lase was replaced by Candela and exact grounded booking used the latest device. |
| 14 | Conditional fallback | Acceptable | P2 | Structured condition was correct, but runtime still evaluated/reported fallback although first choice was available. |
| 15 | Egyptian 12-hour ambiguity | Fully correct | — | “الساعة 2” resolved to the clinic-valid 14:00 slot without guessing an invalid AM time. |
| 16 | Compare doctors then select | Failed | P1 | Doctor set was grounded, but comparison was treated as executable booking and the Agent asked user to choose instead of comparing nearest availability. |
| 17 | Topic switch and resume | Acceptable | P2 | Side PRP price did not destroy booking task, but service was temporarily forgotten before later recovery. |
| 18 | Change mind completely | Fully correct | — | Active booking task cancelled with no business write. |
| 19 | Duplicate customer text | Acceptable | P3 | Only one appointment created; second distinct inbound was treated as unavailable rather than recognized as already booked. |
| 20 | Same-turn corrections | Fully correct | — | Superseded service/date disappeared; final PRP-hair/date/time were used exactly once. |
| 21 | Long returning customer | Acceptable | P2 | History, Pulse read, topic switches, and final booking were grounded; one short doctor follow-up temporarily lost service context. |
| 22 | DB fact vs stale chat | Fully correct | — | Canonical completed PRP visit beat intentionally stale Hydrafacial prose and follow-up retained canonical service. |
| 23 | Long stale-history control | Fully correct | — | 32-message old history did not leak into explicit current Candela booking. |
| 24 | Short control | Fully correct | — | Exact equivalent current booking succeeded with the same final DB state. |

## Long-history stress result

The runtime DB loader is configured for 24 recent messages. The V2 interpreter exposes
at most 6 native dialogue messages per turn and receives durable continuity through
structured active-task / verified-read / verified-action state.
Long-history fixtures contained 32 prior messages, deliberately exceeding the DB
history limit and mixing booking, rescheduling, cancellation, Pulse, package, device,
doctor, and service topics.

Controlled one-turn comparison:

| Metric | Short control | 32-message stale-history control | Delta |
| --- | ---: | ---: | ---: |
| Correct final booking | yes | yes | none |
| LLM calls | 2 | 2 | 0 |
| Input tokens | 6,290 | 6,417 | +2.02% |
| Cached tokens | 4,183 | 4,183 | 0 |
| Uncached tokens | 768 | 823 | +55 |
| Turn latency | 8,322 ms | 9,107 ms | +9.43% |
| Actual cost | $0.00091521 | $0.00105461 | +$0.00013940 |

Observed interpreter exposure never exceeded 6 native history messages. In the
longest 9-turn returning-customer scenario, estimated native-history text peaked at
151 tokens while semantic context peaked at 4,775 tokens. The stress run therefore
shows bounded native history rather than unbounded raw transcript growth.

## Root-cause matrix

### RC1 — Pulse compound offer/overage parameter scoping

A single semantic operation correctly requested both `offers` and `overage_price`,
but the frozen planner forwarded the shared `pulse_count=500` parameter to the
Pulse-pack offer read. The active offer was a 1000-Pulse pack, so the pack read
filtered it out while overage math remained correct.
Affected: scenario 7 (P1).

A concurrent uncommitted planner change already present in the shared worktree removes
`pulse_count` from the offer-side read when overage is also requested. That work is
not part of this evaluation branch.

### RC2 — Financial-ledger semantic misclassification

The frozen interpreter contract explicitly says amounts already paid, balance due,
transactions, refunds, and checkout/settlement for an owned Pulse pack are
Reception-owned and should become `human_support`. The model nevertheless classified
“فاضل عليا كام فلوس” as `pulse_info/owned_packs`.

The hard write boundary prevented any financial mutation and the responder did not
invent a monetary balance, but the required ownership/handoff behavior was missed.

Affected: scenario 8 (P2).

### RC3 — Appointment read drops lifecycle metadata

The frozen `TiaDatabaseClinicAdapter` maps appointment payment fields but omits
`billing_context`, package identity, laser device identity, and visit-group identity
from `AppointmentRecord`. A clean detached-baseline diagnostic with a genuinely
different target slot reproduced the failure: the Agent re-asked for device, then
blocked the reschedule and asked for booking identity instead of completing it.

No payment, Pulse usage, Pulse settlement, or Pulse-balance mutation occurred.

Affected: scenario 9 (P1).
A concurrent uncommitted adapter change already adds the missing appointment metadata.
It is explicitly excluded from this eval branch.

### RC4 — Booking active-task continuation is not adapted consistently

The frozen active-task adapter has special handling for repeated reschedule intent, but
not equivalent BookingTaskState continuation handling. Some booking follow-ups are
therefore replanned from partial model output instead of deterministically merging into
the already verified booking state. This explains safe-but-redundant re-clarification
of date/service in correction and topic-switch flows.

Affected: scenarios 11, 12, 17, 21 (P2).

Concurrent uncommitted work in `active_task_progress.py` adds BookingTaskState
continuation handling and protects verified identities from context-only refs. It is
not part of this evaluation branch.

### RC5 — Same-turn conditional fallback is represented but not enforced

The interpreter produced the correct second operation with
`continuation_condition=if_previous_no_availability`. However, the frozen runtime has
no same-turn planner/orchestrator consumer that suppresses that read after the first
operation proves availability. The responder therefore mentioned the fallback date
even though its condition was false.

Affected: scenario 14 (P2).
### RC6 — Doctor availability comparison is misclassified as booking

The interpreter prompt says direct comparisons should remain informational and a
nearest-availability doctor comparison should use `next_available`. The model grounded
the doctor set and next-available date mode, but emitted `book + execute`. No
deterministic semantic normalizer converts this structured contradiction to an
availability comparison, so the planner correctly treats it as booking and asks the
customer to choose a doctor instead of comparing them.

Affected: scenario 16 (P1).

### RC7 — Responder acknowledgment rough edges

A few flows have correct semantics and DB state but suboptimal conversational finish:
unnecessary Pulse guidance after explicit session-package choice, a redundant
post-cancellation clarification, and duplicate-text wording that says a slot is
unavailable instead of recognizing the just-created appointment.

Affected: scenarios 5, 10, 19 (P3).

## Safety and financial boundary conclusion

No P0 was observed. Across the Pulse scenarios:

- appointment booking never consumed Pulse balance;
- no Agent-created Pulse settlement occurred;
- no fictional payment transaction was created;
- existing Pulse balance did not silently select appointment billing;
- Pulse pack purchase created entitlement without pretending payment was received;
- Pulse-billed cancellation/reschedule diagnostics did not mutate financial ledgers.

The remaining Pulse findings are semantic/read-continuity problems, not unauthorized
financial effects.
## Concurrency and ownership note

While manual review was in progress, unrelated uncommitted runtime changes appeared in
the same shared worktree in:

- `backend/app/integrations/clinic/tia_database.py`
- `backend/app/services/agent_v2/active_task_progress.py`
- `backend/app/services/agent_v2/planner.py`
- related backend tests

Those changes align with RC1, RC3, and RC4, but they were not authored, staged, or
committed by the Batch 02 evaluation work. The raw baseline and root-cause conclusions
remain tied to the frozen runtime base `adebcf54...`.

## Release decision for this task

Batch 02 evaluation itself is ready to merge as evaluation tooling/reporting only.

Runtime fixes remain a separate follow-up track. The reviewed baseline must remain the
comparison point for any fix verification, with special attention to P1 scenarios 7,
9, and 16 and P2 scenarios 8, 11, 12, 14, 17, and 21.
