# Batch 3 Root-Cause Analysis — 2026-09-25

Runtime baseline: `64fc422ebb9b35e0df12fcd260bc1986c9cf1032`

This document analyzes Batch 3 failures only. It intentionally contains **no Agent runtime patch**.

## Failure cluster F1 — Financial ownership intent collapses into active-service pricing

Affected scenario: **S1 — handoff during active booking**

Severity: **P1**

### Evidence

The customer had an active laser-underarm/Candela booking task, then asked:

> طب وفاضل عليا كام فلوس؟

The structured interpretation emitted a `pricing` operation for the active laser service/device. The planner performed only a `service_catalog` read and the final answer was the current session price, 650 EGP.

Expected ownership was a Reception handoff for the outstanding financial balance. No handoff was created.

No payment, Pulse, or ledger write occurred, so this is not P0. The failure is semantic ownership/correctness, not financial mutation.

### Code-level cause

The V2 interpreter prompt has a strong financial-ledger marker for **Pulse** questions: `requested_pulse_details=[financial_ledger]` is defined for money already paid, money still due, payment status, settlement, etc.

There is no equally explicit generic typed financial-ledger marker for an appointment/customer balance question. In an active booking context, the interpreter can therefore inherit the active service/device and reinterpret “money still due” as ordinary service `pricing`.

The deterministic normalizer can only enforce human ownership when the interpreter emits a structured ownership marker. It cannot safely recover this case without inspecting raw customer text, which the architecture intentionally avoids.

### Solution options

**Option F1-A — Recommended: generic typed financial-ledger ownership operation/marker**

Add a domain-neutral semantic marker such as `financial_ledger` / `financial_concern` that is independent of Pulse/service pricing. Python normalization maps it to Reception ownership and never authorizes a financial read by itself. Safe Agent-owned companion reads may coexist only when separately requested.

- Correctness: high
- Added LLM tokens: near zero
- Runtime latency: near zero
- Complexity: medium
- Regression risk: low-medium with contract tests
- Architectural fit: strong; preserves semantic routing and no raw-text keyword rules

Required tests should include the same wording both inside and outside an active booking, mixed safe-info + ledger questions, and unrelated service-price questions to ensure pricing still works.

**Option F1-B — Extend the existing structured detail contract**

Introduce `requested_financial_details` on an informational operation and normalize any current-balance/payment-status/settlement detail to `human_support`.

- Correctness: high
- Token impact: low
- Complexity: medium
- Regression risk: medium because it expands a cross-domain contract
- Architectural fit: good

**Option F1-C — Prompt-only clarification of generic financial ownership**

Teach the interpreter more explicitly that “money still due / paid / settlement” is Reception-owned even under an active service task.

- Correctness: medium
- Complexity: low
- Regression risk: medium-high because the deterministic layer still has no generic ownership marker
- Architectural fit: weaker than F1-A

Do not fix this with regex/keyword routing over Arabic text.

---

## Failure cluster F2 — Reschedule source appointment and replacement constraints share one parameter bag

Affected scenarios: **S4, S5, S6, S15**

Severity: **P1**

### Evidence

Across all four failures, the customer supplied a **replacement** date/time. The plan then sent that replacement date/time to both reads:

- `appointments(parameters=params)`
- `availability(parameters={**params, "reschedule": True})`

The appointment read returned zero source matches, so the write was correctly blocked.

S5 and S6 are especially diagnostic because the user explicitly named the **current/source appointment date** and the **new/replacement date** in the same turn. The structured contract retained the replacement in `entities.date`, while the source date was only natural-language appointment text. The planner then reused the replacement date for source appointment discovery.

S15 proves package integrity is not the problem: the original package-backed booking and its reserved `PackageUsage` remained correct and untouched; only the reschedule could not resolve its source appointment.

### Code-level cause

In `backend/app/services/agent_v2/planner.py`:

- `_base_parameters()` places `operation.entities.date` and `time` directly into one generic `params` object.
- The reschedule branch reuses that same `params` for the source `appointments` read and the destination `availability` read.
- `backend/app/services/agent_v2/read_executor.py::_read_appointments()` filters current appointments when `params["date"]` is present.

This conflates two different identities:

1. **Source appointment selector** — which existing appointment is being changed.
2. **Replacement constraints** — where/when the customer wants to move it.

The write executor is not the root cause. It is failing closed because the verified source appointment is missing.

### Solution options

**Option F2-A — Recommended: typed source/destination separation in the plan contract**

Represent reschedule data as two independent structures:

- `source_appointment`: canonical appointment id/ref or source-selection constraints.
- `replacement`: destination date/time/doctor/device constraints.

Resolve the source appointment first. Only after exactly one source is verified should replacement availability be checked and a write become eligible. Persist immutable source facts needed for lifecycle integrity: appointment id, service, doctor, device, billing context, package id/usage linkage.

- Correctness: very high
- Token impact: negligible
- DB reads: same order of magnitude; can remain one source read + one availability read
- Complexity: medium
- Regression risk: low-medium with typed migration/tests
- Maintainability: high

**Option F2-B — Two-phase planner without changing the turn schema**

Keep the current turn contract, but construct separate read parameter dictionaries in the planner. Strip destination `date/time` from the `appointments` read unless a canonical source appointment ref/date has been explicitly resolved. Then merge verified source facts into the availability request.

- Correctness: high for observed failures
- Complexity: low-medium
- Regression risk: medium, especially for turns that mention both old and new dates
- Maintainability: medium

This is smaller but still needs a deterministic way to preserve an explicitly stated source date from S5/S6; otherwise the source-date phrase remains trapped in free-form appointment text.

**Option F2-C — Dedicated lifecycle resolver/state machine**

Create a deterministic `RescheduleTarget` + `ReplacementRequest` resolver that owns candidate discovery, source selection, destination availability, and write authorization.

- Correctness: very high
- Complexity: high
- Regression risk: medium during introduction
- Maintainability: high once mature
- Best use: if cancellation/confirmation/reschedule continue accumulating shared lifecycle ambiguity rules

---

## Failure cluster F3 — Lifecycle choice scope and appointment-state persistence

Affected scenarios: **S7 (P2), S8 (P1), S9 (P1)**

### Evidence

### S7

“عايزة أغير ميعاد الليزر” failed safely, but the interpreter expanded “laser” into the full service catalog and asked the customer to choose a service. The patient actually had two current laser-underarm appointments that could have been read first and presented as the real lifecycle ambiguity.

No write occurred. This is a safe but unnecessary clarification: P2.

### S8

The first turn correctly read the two actual appointments and presented two appointment choices. However, the resulting choice set was not retained as a durable active lifecycle target.

On “التاني”, the interpreter reconstructed the selected appointment's service/doctor/current date/current time and the planner treated those current values as a fully authorized replacement request. It executed a real reschedule write whose replacement time was identical to the selected appointment's existing time — a no-op lifecycle mutation that should never have happened before the customer supplied a new destination.

The next turn supplied the actual new date/time, but the source appointment/device was no longer durably bound; the planner re-entered destination-filtered appointment discovery and asked for the laser device again.

### S9

The first cancellation turn expanded generic “laser” into service-catalog candidates before reading the patient's current appointments. “التاني” therefore selected the second **service** candidate (underarm+bikini), not the second **appointment**. The appointment read returned zero rows and cancellation never happened.

No wrong appointment was cancelled, so the failure remains P1 rather than P0.

### Code-level cause

Two rules interact badly:

1. In `planner._plan_operation()`, ambiguous `service` is clarified **before** appointment ambiguity is resolved.
2. Lifecycle appointment choices generated from verified reads are not always persisted as a scoped active lifecycle option snapshot that forces the next ordinal selection through `select_active`.

For reschedule, the selected appointment's current date/time can also be mistaken for replacement authorization because the source/destination model is not separated (F2).

### Solution options

**Option F3-A — Recommended together with F2-A: appointment-first lifecycle resolution + durable scoped choice state**

For `cancel_appointment`, `confirm_appointment`, and `reschedule`:

- If no exact service/appointment ref is supplied, read current actionable appointments before asking for catalog service disambiguation.
- Present only verified current-appointment candidates.
- Persist a scoped lifecycle option snapshot with appointment ids and provenance.
- Bind ordinal/ref selection only to that snapshot.
- Selecting the source appointment must **not** authorize a reschedule destination write.
- After source selection, ask for replacement constraints if missing.

- Correctness: very high
- Complexity: medium
- Token impact: usually lower because irrelevant catalog choices disappear
- Regression risk: low-medium
- UX: substantially better

**Option F3-B — Lifecycle-specific candidate precedence in the interpreter/planner**

Keep current state structures but change precedence so generic service ambiguity does not block an appointment read for lifecycle operations. Use service catalog clarification only if current appointments themselves still span multiple unresolved service meanings after the read.

- Correctness: high for S7/S9
- Complexity: low-medium
- Regression risk: medium
- Does not fully solve S8 without source/destination separation

**Option F3-C — Require explicit `select_active` for any ordinal reply to a verified appointment-choice response**

Whenever the previous grounded outcome exposed appointment choices, force the next ordinal/ref response through the typed option snapshot rather than reconstructing a new lifecycle operation from prose.

- Correctness: high for choice binding
- Complexity: medium
- Regression risk: low if snapshot TTL/scope guards remain strict
- Does not alone solve destination authorization; combine with F2-A/F2-B

---

## Recommended repair sequence

1. **F1-A** — add generic typed financial ownership semantics and deterministic handoff normalization.
2. **F2-A + F3-A** — separate source appointment from replacement constraints and make lifecycle candidate selection appointment-first/persistent.
3. Add deterministic tests before live reruns.
4. Run targeted live gates: S1, S4–S9, S15.
5. Re-run all RC1–RC7 deterministic controls.
6. Re-run all 22 Batch 3 scenarios unchanged.

Do not add raw-text keyword/regex routing. Do not loosen verified-read-before-write requirements. Do not move financial settlement into the Agent.
