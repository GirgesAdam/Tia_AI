# Root-Cause Task — Batch 2 Scenario 22 Verified-Fact Continuity Regression

## Status

**Open — implementation intentionally deferred.**

This task was created by the Batch 2 integrated closeout on `c9d59cdb7863439d0faa2f352b5cb471dad7e7ba`. It must be implemented in a separate runtime branch/task; the closeout branch contains evaluation artifacts only.

## Failure

- Scenario: `b2_22_long_db_wins_over_stale_chat`
- Severity: **P1**
- Root layer: **Context / continuity + state management**
- Safety impact: no wrong write, financial mutation, or cross-tenant exposure occurred.
- Product impact: the Agent degraded a verified canonical business fact into ambiguity and failed to continue the user's requested booking from that fact.

## Evidence

1. Turn 1 — customer: “أنا عملت إيه آخر مرة؟”
   - canonical `customer_history` read executed.
   - verified result: last completed service = **PRP للبشرة**.
   - reply correctly stated PRP skin.
2. Turn 2 — customer challenged the result using intentionally stale chat prose mentioning Hydrafacial.
   - interpreter produced a `customer_history` continuation.
   - no canonical read executed.
   - reply incorrectly presented PRP and Hydrafacial as unresolved alternatives.
3. Live V2 creates `v2_read_context` from **the current turn only** via `_verified_read_context_from_turn(...)`.
   - because turn 2 performed no read, the outbound message persisted `v2_read_context=None`.
   - `_recent_verified_read_context(...)` only inspects the immediately previous outbound message.
4. Turn 3 — customer: “عايزة أحجز نفس الحاجة اللي عملتها فعلًا آخر مرة”
   - no recent verified-read fact was available.
   - Agent again asked PRP vs Hydrafacial instead of using the canonical PRP fact.
5. The original reviewed Batch 2 marked Scenario 22 Fully Correct, so this is a cross-regression rather than an unresolved original finding.

## Root cause

Verified read state is intentionally short-lived, but its current persistence rule is too aggressive for a **no-read continuation**. A safe canonical fact can disappear after one conversational challenge/acknowledgment even when the next turn still depends on exactly that fact.

The issue is not the DB read itself and not the canonical history implementation. It is the handoff from one verified read to the next turn when an intermediate continuation produces no new read context.

## Option A — bounded carry-forward of the previous verified read (recommended)

When the current turn produces no new verified read, preserve the previous `v2_read_context` for exactly one additional outbound **only if** the current structured operation is an explicit continuation of the same semantic operation/fact scope.

Suggested deterministic guards:

- current turn has no new verified read;
- exactly one prior safe `recent_verified_read` exists;
- current operation has `continues_previous=true`;
- operation family/scope is compatible with the prior verified read;
- no new explicit entity/dimension conflicts with the prior fact;
- carry-forward has a one-hop TTL and is cleared on topic switch, explicit correction, handoff, or unrelated read/write.

### Trade-offs

- Correctness: **High** — preserves the exact verified fact the user is still discussing.
- Reliability: **High** with strict scope/TTL.
- Complexity: **Low–medium**.
- Maintenance: **Low**; localized to verified-context persistence.
- Token impact: **Near zero**; reuses a compact existing semantic view.
- Latency: **No material increase**; no additional DB/LLM call.
- Regression risk: **Medium if overly broad**, **low with same-operation + one-hop guards**.
- Architecture fit: **High** — keeps verified DB facts above conversation prose without adding keyword/regex routing.

## Option B — force canonical re-read on verified-fact continuations

Whenever a customer challenges or continues a prior `customer_history` fact, planner/orchestrator performs a fresh canonical `customer_history` read before responding. For an anaphoric booking such as “same thing I actually did last time,” resolve the referenced service by a new canonical read before booking progression.

### Trade-offs

- Correctness: **Very high**.
- Reliability: **High**.
- Complexity: **Medium**; planner rules must distinguish fact-dependent continuations from ordinary prose.
- Maintenance: **Medium**.
- Token impact: **Low**.
- Latency: **Small DB-read increase**.
- Regression risk: **Low–medium**.
- Architecture fit: **High**, but duplicates reads that are often still fresh.

## Option C — durable scoped canonical-fact state

Introduce a small durable semantic state object for facts such as “last completed service,” with explicit provenance, fact type, value/ref, source read, TTL, and invalidation rules.

### Trade-offs

- Correctness: **High**.
- Reliability: **High if invalidation is perfect**.
- Complexity: **High**.
- Maintenance: **High**.
- Token impact: **Low–medium** depending on schema exposure.
- Latency: **Low**.
- Regression risk: **Medium** because stale-fact invalidation becomes a new state machine.
- Architecture fit: **Reasonable but overbuilt for the observed failure**.

## Recommendation

Implement **Option A**: a **bounded, one-hop, same-topic verified-read carry-forward**. It is the smallest production-reliable change that preserves the canonical fact through a no-read continuation while keeping stale-context risk controlled.

Do **not** carry verified read state indefinitely. Do **not** use raw-text matching, keywords, or regex to detect “last time” language. Use the existing structured operation, `continues_previous`, canonical references, and deterministic scope comparison.

## Deterministic tests

Add tests for:

1. verified customer-history fact survives one no-read `continues_previous=true` turn;
2. same fact is available to the next dependent booking interpretation;
3. topic switch clears carry-forward;
4. explicit correction clears/replaces incompatible fact context;
5. unrelated read replaces the prior fact rather than merging it;
6. carry-forward expires after the bounded hop;
7. tenant/workspace isolation remains unchanged;
8. recent verified action context is not broadened or conflated with verified read context;
9. Scenario 19 duplicate-booking acknowledgment still requires strict recent-action match;
10. Scenario 10 already-cancelled acknowledgment still requires strict recent-action match.

## Live gate

After implementation, run on a fresh frozen SHA:

1. Scenario 22 alone with the exact Batch 2 fixture/messages.
2. Long-history regression set: Scenarios 21–24.
3. RC7 safety regressions: Scenarios 10 and 19 to ensure carry-forward cannot create false duplicate/already-cancelled acknowledgments.
4. RC4 continuation regressions: Scenarios 11, 12, 17, 21.
5. Full Batch 2 closeout again if the runtime change lands on main.

Required Scenario 22 result:

- turn 1 canonical last service remains PRP skin;
- stale Hydrafacial prose never becomes co-equal with the verified DB fact;
- “same thing I actually did last time” resolves to PRP skin or, if booking still lacks date/time, asks only for the genuinely missing booking dimensions;
- no wrong appointment write;
- no old-context leakage.

## Regression scope

Primary:

- `backend/app/services/agent_v2/live_chat.py`
- verified-read context persistence/loading
- semantic state exposure of `recent_verified_read`

Must revalidate:

- customer-history follow-ups;
- booking continuations after informational turns;
- topic switches;
- stale-history controls;
- recent-action acknowledgments;
- conditional availability continuation;
- no expansion of financial reads or writes.

## Acceptance

The task is complete only when Scenario 22 returns to Fully Correct on live evaluation without introducing a failure in Scenarios 10, 11, 12, 14, 17, 19, 21, 23, or 24, and full CI is green.
