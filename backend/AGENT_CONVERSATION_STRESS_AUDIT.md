# Tia customer-agent conversation stress audit

This audit is a live regression suite for the real customer-agent runtime. It is intentionally broader than the older E2E matrix: the full catalog contains **214 customer turns** (113 semantic turns + 101 stateful E2E turns) across more than 30 multi-turn conversations.

## What it covers

- Service discovery, pricing, duration and mixed price+booking questions.
- Branch and doctor discovery, addresses, recurring working hours and bookability.
- Arabic/Egyptian Arabic, English, mixed Arabic/English, Franco Arabic and common shorthand.
- Relative dates, exact times, before/after constraints, time ranges and corrections.
- Fresh booking, exact slot selection, option selection by index/time, requirement relaxation and requirement replacement.
- Cross-date “nearest available” requests.
- Appointment list, confirmation, cancellation and rescheduling.
- Multiple-upcoming-appointment ambiguity and destructive-write prevention.
- Switching from a failed/stale reschedule flow into a fresh booking.
- Topic switches inside a booking flow, then returning to the original task.
- Customer profile/history and historical payments.
- Package remaining sessions, package use and package refund questions.
- Marketing consent opt-out/opt-in and rejecting one offer without global opt-out.
- Explicit future follow-up requests and missing-time clarification.
- Medical suitability, pregnancy, medication, adverse-event/urgent language and complaint/payment handoff.
- Explicit human-support requests.
- Blocked-patient behavior.
- Other-customer privacy requests, system-prompt/UUID requests, prompt injection and destructive SQL requests.
- Long-context topic churn and workflow memory.

## Evaluation principles

The suite does not pass a turn just because Tia returned fluent text. It records the real AgentAction rows for each run and checks expected/forbidden tools, unexpected handoff, UUID leakage, missing replies and availability claims that are not backed by a verified availability read.

Every E2E scenario runs inside a database savepoint. The whole suite is wrapped in an external transaction and rolled back. The runner refuses production and refuses a demo environment where external dispatch is enabled.

## Baseline architecture findings intentionally tracked

The audit documents known structural risks before any repair so the same matrix can compare before/after behavior:

1. No deterministic cross-date next-available operation.
2. `get_customer_packages` exists but has no semantic capability/policy path.
3. Human handoff is exposed even when the current semantic policy did not require it.
4. Grounded response coverage is capability-generic instead of requiring capability-specific verified reads.
5. Active booking/reschedule flow capabilities can be inherited into an incompatible new task.
6. There is no customer-facing deterministic package refund quote surface.
7. The complex unified turn interpreter currently defaults to Flash-Lite/minimal thinking and must be benchmarked against stronger realtime options using this matrix.

## Run

Use the isolated demo database and keep external dispatch disabled:

```powershell
python scripts\run_agent_conversation_stress.py --workspace-slug tia-demo --profile full --max-turns 220
```

The report is written to:

```text
backend/artifacts/agent-conversation-stress-report.json
```

A non-zero exit code is expected on the **baseline** while known failures still exist. Do not treat that as a runner crash; inspect the JSON summary and per-turn findings.
