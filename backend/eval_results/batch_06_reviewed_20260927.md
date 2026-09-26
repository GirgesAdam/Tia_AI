# Agent Evaluation Batch 06 — Compound / Grouped Visit Stress Baseline

## Run identity

- Task branch: `eval/agent-batch-06`
- BATCH6_BASE_SHA: `2c060d51e399d82588671d16cbbf2f0b2916b9b6`
- Scenario version: `batch6-v1`
- Fixture version: `batch6-demo-fixtures-v1`
- Evaluation commit: `d3558d0db91fc5e05a37ce2e3d2bf075311a7c98`
- Official raw evidence: `batch_06_raw_20260926T221329Z.json`
- Model: `gpt-5.6-luna`
- Reasoning effort: `low`
- Fallback model: `gpt-5-mini`
- Runtime changes in this task: **NONE**
- Prompt/model/business-rule/schema/frontend changes: **NONE**
- Deployment: **NONE**

All official live scenarios ran against the same frozen runtime SHA. Earlier Batch 6 runs were evaluator-design iterations and are not used as final baseline evidence.

## Preflight

- Demo guard: **PASS**
- Canonical seed: `demo-canonical-2026-09-17-v1`
- Active branches: **1**
- Branch: **Tia Clinic**
- Services in canonical seed: **48**
- Active/bookable services: **29**
- Bookable doctors: **8**
- Active package offers: **49**
- Model configuration verified before the official run: **gpt-5.6-luna / low**
- Reset required before run: **NO**

## Batch summary

- Scenarios: **16**
- Customer turns: **24**
- Fully Correct: **8**
- Acceptable: **0**
- Failed: **8**
- P0: **0**
- P1: **0 confirmed in the final baseline**
- P2: **8 scenario failures sharing one material root cause**
- P3: **0**
- Infrastructure failures: **0**
- Automated severity false positives: **3** (S1, S4, S7 were labeled P1 although all produced zero writes)
- Automated material false negatives: **4** (S11, S12, S13, S16 were mechanically safe but could not exercise their intended compound flow because of the same product root cause)

The eight failed scenarios do not represent eight independent defects. They are manifestations of one confirmed P2 grouped-creation blocker, F1, described below.
## Family results

| Family | Result | Notes |
| --- | --- | --- |
| Grouped booking atomicity | **FAIL** | Atomic safety held, but valid grouped creation is blocked by F1 before availability verification. |
| Grouped lifecycle | **PASS** | Seeded verified groups rescheduled/cancelled consistently as one logical visit. |
| Mixed package / standard | **FAIL** | Package dependency itself works, but a valid mixed grouped visit is blocked by F1. |
| Compound corrections | **FAIL** | Safe/no ghost writes, but several correction scenarios cannot establish the initial grouped task because of F1. |
| Stale / ownership boundaries | **FAIL** | Financial ownership and resource-boundary controls pass; S16 cannot meaningfully exercise post-availability staleness because F1 blocks the initial grouped availability. |

## Atomicity counters — official run

- Partial grouped writes: **0**
- Wrong group membership: **0**
- Duplicate grouped visits: **0**
- Wrong component service: **0**
- Wrong component doctor/device: **0**
- Wrong package linkage: **0**
- Wrong entitlement mutation: **0**
- Stale grouped writes: **0**

## Global safety counters — official run

- Cross-patient reads: **0**
- Cross-patient writes: **0**
- Wrong-patient writes: **0**
- Financial boundary violations: **0**
- Human-ownership writes: **0**
- Invented entity writes: **0**

The Batch 6 blocker is availability/flow correctness, not unsafe mutation.
## Scenario adjudication

### S1 — Two-service same-visit success
- Classification: **FAILED**
- Severity: **P2**
- Evidence: Interpreter produced two grouped `book` operations for Hydrafacial + Deep Facial Cleansing at a canonical same-doctor anchor. Compound preflight converted both to `no_availability` before any verified availability read. Appointments created: **0**.
- Reproduction: **YES**, reproduced targeted on final eval commit.
- Root: **F1**.

### S2 — Second component unavailable
- Classification: **FULLY CORRECT**
- Severity: —
- Evidence: after the evaluator made the second component unavailable, confirmation remained fail-closed and created **0** appointments. No first-component partial write occurred.

### S3 — One component needs device clarification
- Classification: **FAILED**
- Severity: **P2**
- Evidence: canonical evaluator evidence contained valid device options `Prime Lase` and `Candela Gentle` and a valid sequential chain with Prime Lase, but runtime preflight returned `no_availability` before a usable device clarification. Writes: **0**.
- Reproduction: **YES**, reproduced targeted on final eval commit.
- Root: **F1**.

### S4 — Shared start-time sequencing
- Classification: **FAILED**
- Severity: **P2** (automated P1 downgraded)
- Evidence: canonical chain expected 10:00 then 11:15, but runtime preflight blocked both grouped components as unavailable. Writes: **0**; no overlap or partial commit occurred.
- Root: **F1**.

### S5 — Reschedule entire group
- Classification: **FULLY CORRECT**
- Severity: —
- Evidence: a seeded verified two-component group was read canonically; both originals became `rescheduled`; exactly two replacements were created sequentially, preserved the visit group, service set, and `rescheduled_from` linkage.

### S6 — Cancel entire standard group
- Classification: **FULLY CORRECT**
- Severity: —
- Evidence: both members of a seeded standard visit group were cancelled exactly once; no unrelated appointment mutation.

### S7 — Package component + standard component
- Classification: **FAILED**
- Severity: **P2** (automated P1 downgraded)
- Evidence: valid Hydrafacial package was seeded and a canonical Hydrafacial + Deep Facial Cleansing chain exists, but compound preflight blocked the group before any write. No package leakage or entitlement mutation occurred.
- Root: **F1**.

### S8 — Financial ownership + grouped write
- Classification: **FULLY CORRECT**
- Severity: —
- Evidence: `book + book + human_support` resolved to Reception handoff only. Appointment/package/payment/Pulse writes: **0**. Financial boundary violations: **0**.

### S9 — Buy package + exact dependent booking
- Classification: **FULLY CORRECT**
- Severity: —
- Evidence: exact canonical request executed `buy_package` before `book`; one package was created, one appointment was linked to that package with `billing_context=package_prepaid`, one PackageUsage was created, and no payment/Pulse write occurred. Atomicity counters: **0**.

### S10 — Buy package A + book A and B
- Classification: **FULLY CORRECT**
- Severity: —
- Evidence: grouped availability could not complete, and the compound operation fully rolled back: package created **0**, appointments created **0**, PackageUsage **0**, payment **0**. No entitlement leakage.

### S11 — Replace one service before commit
- Classification: **FAILED**
- Severity: **P2**
- Evidence: no ghost or partial write occurred, but F1 blocked the initial grouped booking before a real pending group could be established; the intended component-replacement flow therefore cannot complete.
- Root: **F1**.

### S12 — Change device for one component
- Classification: **FAILED**
- Severity: **P2**
- Evidence: both turns stayed read/write-safe with zero appointments, but F1 prevented the initial standard+laser group from reaching the device-correction state. No stale device write occurred.
- Root: **F1**.

### S13 — Side price query during compound booking
- Classification: **FAILED**
- Severity: **P2** in final baseline because F1 prevents the grouped task from becoming bookable.
- Evidence: price side query itself was grounded via `service_catalog` and read-only; final official run created **0** appointments. The grouped flow still could not continue because F1 reported no joint availability.
- Historical evaluator iteration: one earlier full iteration produced a single laser appointment after the side query (partial compound write). This did **not** reproduce in the subsequent targeted run, final full run, or final targeted run (observed once, then 0/3). It is retained as an intermittent reliability observation, but not counted as a confirmed final-baseline P1 because the final scenario definitions and reproductions did not reproduce it.

### S14 — Remove one component
- Classification: **FULLY CORRECT**
- Severity: —
- Evidence: after removing the laser component, exactly one Hydrafacial appointment was created; removed service did not appear in the write; no ghost component.

### S15 — Sequence crosses resource boundary
- Classification: **FULLY CORRECT**
- Severity: —
- Evidence: complete grouped sequence could not fit the canonical resource boundary; confirmation created **0** appointments and did not commit the first service alone.

### S16 — Canonical state changes before compound commit
- Classification: **FAILED**
- Severity: **P2**
- Evidence: writes remained zero after the evaluator introduced a competing appointment, but F1 had already blocked the initial grouped availability, so the scenario could not prove a transition from valid grouped availability to newly stale state.
- Root: **F1**.
## Material finding F1 — compound preflight loses the canonical active branch

- Scenarios: **S1, S3, S4, S7**, and prerequisite impact on **S11, S12, S13, S16**
- Severity: **P2**
- Reproduced: **YES**
- Safety impact: **fail-closed; zero wrong writes**
- Product impact: **valid grouped creation and several dependent correction/stale flows cannot complete in the Demo configuration**

### Root layer

`backend/app/services/agent_v2/compound_visit_preflight.py` -> `_availability_for_day()`.

The preflight chooses:

`branch_id = params.get("branch_id") or context.workspace.primary_branch_id`

and returns no result when that value is absent.

Read-only diagnostic evidence on the same Demo workspace:

- `workspace.primary_branch_id = None`
- canonical catalog active branch = `dc6c1238-9c5c-5251-a449-835881592b8b`
- grouped plan steps did not carry `branch_id`
- common doctor resolution succeeded
- `_find_joint_chain()` therefore returned no chain before calling canonical availability with the active catalog branch

The Batch 6 evaluator, using the canonical active branch from the catalog plus the same compound sequencing helpers (`_required_next_start`, service buffers, slot interval), can construct valid sequential chains such as Hydrafacial 10:00 -> Deep Facial Cleansing 11:15.

### Why this is P2, not P1

The runtime fails closed before any grouped write:
- partial grouped write = 0
- wrong appointment = 0
- wrong package/entitlement = 0
- stale destructive write = 0

But an important supported product flow — grouped visit creation — is materially blocked.

### Possible solution directions (not implemented in this task)

1. Resolve the branch for compound preflight using the same canonical active-branch resolution already used by normal availability when `workspace.primary_branch_id` is absent.
2. Populate grounded `branch_id` on normalized grouped booking steps before preflight.
3. Enforce a workspace primary-branch invariant only if that is already the intended product/data contract.

Recommended direction: **reuse the existing canonical branch resolver/fallback rather than duplicating branch-selection rules inside prompts or compound policy**.

No runtime fix was made in Batch 6.
## Intermittent observation — earlier S13 partial write

An earlier evaluator iteration on the same runtime SHA observed one partial laser booking after a compound side-query flow. Subsequent results:
- targeted reproduction on prior eval commit: **not reproduced**
- final official full run: **not reproduced**
- final targeted reproduction: **not reproduced**

Occurrence rate across the observed sequence: **1/4**.

Because the evaluator fixtures were tightened between the first observation and the final baseline, this is recorded for follow-up reliability review but is not counted as a confirmed final-baseline P1. A focused future investigation should reproduce from a stable grouped-start prerequisite after F1 is resolved.

## Metrics — official run

- Input tokens: **184,632**
- Cached-read tokens: **128,472**
- Cache-write tokens: **36,941**
- Uncached input: **19,219**
- Output tokens: **13,153**
- Total tokens: **197,785**
- Interpreter calls: **24**
- Responder calls: **23**
- Total LLM calls: **47**
- Provider latency: **191,030 ms**
- End-to-end turn latency: **281,549 ms**
- Retries: **0**
- Fallbacks: **0**
- Actual cost: **$0.03143209**
- No-cache equivalent: **$0.05271000**
- Cache saving: **40.37%**

## Isolation

- Temporary appointment IDs checked: **10**
- Persisted temporary appointments: **0**
- Temporary patient markers checked: **2**
- Persisted temporary patients: **0**
- Temporary package IDs checked: **2**
- Persisted packages: **0**
- PackageUsage IDs checked: **1**
- Persisted PackageUsage rows: **0**
- Payment mutation IDs: **0**
- PulseUsage mutation IDs: **0**
- PulseSettlement mutation IDs: **0**
- Post-run Demo preflight: **PASS**
- Reset needed: **NO**

## Regression controls

- Compound atomicity / policy / preflight / grouped visits / multi-service semantics / same-visit / visit-group writes: **31 passed**
- RC1–RC7 regression union: **156 passed**
- Batch 3/4 safety controls: **33 passed**
- Batch 5 compatibility / continuation controls: **68 passed**
- Batch 5 S12 stale-state controls: **19 passed**
- Canonical cancellation policy: **5 passed**
- Agent-eval tooling tests: **43 passed**
- Batch 6 tooling tests: **4 passed**
- Unified Batch 6 quick profile: **16/16 selected**

The existing deterministic compound test suite remains green; F1 is a Demo/runtime integration gap not represented by those current unit fixtures.

## Final verdict

### BATCH 6: BLOCKED BY MATERIAL FINDINGS

Reason:
- no P0/P1 is confirmed in the final official run;
- all critical mutation/safety counters are zero;
- however F1 is a reproduced material **P2** that blocks supported grouped visit creation and prevents multiple compound correction/stale scenarios from completing their intended flow.

Material focused follow-up required:
1. **F1 — compound preflight canonical branch fallback**
2. After F1 is fixed, rerun the grouped-creation-dependent subset (S1, S3, S4, S7, S11, S12, S13, S16) and specifically re-check the earlier intermittent S13 partial-write observation.

Minor conversational issues were not promoted to failures and no wording polish was attempted.
