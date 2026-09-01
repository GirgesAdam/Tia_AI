# Phase 8 Architecture Review

## Decision

Do **not** copy the Analytics catalog architecture wholesale into Automations.

Analytics needed deterministic computation because numbers, patient eligibility and financial attribution must be reproducible. Automations have a different shape: they combine authoring, triggers, conditions, content, execution, retries and ongoing conversations. The right Phase 8 design is therefore a **policy-constrained hybrid workflow runtime**.

## What should remain deterministic

These parts are correctness/safety boundaries and must not depend on an LLM decision at runtime:

- canonical patient/appointment/payment/campaign identity;
- trigger facts and time calculations;
- audience eligibility and exclusions;
- consent, block-list and channel-route checks;
- financial/analytics conditions and thresholds;
- deduplication, idempotency, retry/backoff and job state transitions;
- rate limits, maximum audience sizes and quiet-hour rules;
- writes to appointments, CRM tasks, campaigns and payment facts;
- audit history and the exact reason a workflow did or did not run.

## Where AI is useful

AI should be used where language/context is the hard part rather than truth evaluation:

1. **Automation authoring** — an admin can describe a goal in normal language. AI translates it into a typed `AutomationSpec` draft. The UI then shows the exact trigger, conditions, audience, schedule and actions before activation.
2. **Message/content generation** — generate or adapt message copy within channel/template constraints. Provider-approved WhatsApp templates remain authoritative when required.
3. **Conversation continuation** — after an automated message receives a reply, the existing agent can understand the patient's language and choose from allowed clinic tools. Tool permissions and write confirmations remain enforced by backend policy.
4. **Summaries and recommendations** — AI can explain why an alert fired or summarize an automation run, but it does not decide the underlying numeric truth.

AI should not be called on every scheduled tick merely to rediscover a rule that is already known. That would add latency, cost and variance without adding useful intelligence.

## Runtime shape

Use two trigger paths behind one workflow model:

- **Event-driven triggers** for appointment created/confirmed/completed/no-show/cancelled, payment/refund, campaign delivery/reply and other state changes. Emit durable internal events/outbox facts and evaluate matching workflows immediately.
- **Scheduled evaluation** for conditions such as lapsed patients, daily reports, inactivity windows, weekly thresholds or aggregate alerts.

Both paths create the same idempotent Automation Jobs and execute through the existing worker/outbox machinery. n8n may remain an execution/integration worker, but Tia's database owns workflow state, dedupe keys, approvals and audit truth.

## Suggested AutomationSpec boundary

The stored workflow should be typed and versioned, conceptually containing:

- trigger: event or schedule;
- conditions: canonical field/metric predicates;
- audience: optional patient cohort query;
- actions: ordered, explicitly allowed tools/actions;
- content policy: fixed template, AI-assisted copy, or no outbound message;
- approval policy: always automatic, approve first run, approve every run, or approve above a risk threshold;
- limits: audience cap, frequency cap, quiet hours, channel restrictions;
- failure policy: retry/backoff, pause threshold and escalation target.

Natural language is an **input method for producing this spec**, not the persisted execution logic.

## Risk tiers

A single approval model is not appropriate for every automation:

- Low risk: internal daily summaries, reminders already approved by clinic policy — may run automatically.
- Medium risk: one-to-one patient follow-ups — can run automatically after explicit workflow activation, with consent/rate/frequency guards.
- High risk: bulk campaigns, destructive record changes, financial changes or unusually large audiences — require explicit confirmation or a pre-approved bounded policy.

## Existing Phase 7 assets to reuse

- Analytics catalog functions can serve as trusted condition/audience primitives when an automation needs a metric or cohort.
- Saved Views can become reusable references for admin-authored conditions, but a workflow should persist a versioned typed spec rather than depend on mutable UI state.
- Campaign conversion tracking provides outcome signals for automation effectiveness.
- The isolated Analytics DB pool is useful for scheduled aggregate conditions so reporting work cannot starve booking operations.
- Existing `automation_rules`, `automation_jobs`, workers, dispatch outbox and activity audit provide a base runtime, but the current rule model is appointment-centric and must be generalized rather than multiplied into many hard-coded rule types.

## Phase 8 entry criteria

Before implementation, define the typed workflow spec, event taxonomy, approval/risk policy and ownership between Tia and n8n. Only then should the current appointment-specific automation engine be generalized.
