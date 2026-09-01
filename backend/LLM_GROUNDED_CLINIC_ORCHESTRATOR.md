# Tia v0.19.2 — LLM-Grounded Clinic Orchestrator

## Runtime contract

The active customer runtime uses one semantic language layer and deterministic execution boundaries:

```text
Customer message
  -> PostgreSQL clinic catalog snapshot
  -> Unified LLM turn interpreter
       - capabilities / safety
       - canonical service / doctor / branch IDs
       - date / exact time / time range
       - candidate canonical IDs when genuinely ambiguous
  -> Python validation / capability policy / flow CAS
  -> PostgreSQL read or write tools using canonical IDs
  -> Grounded LLM response composer using verified data only
  -> WhatsApp / API response
```

## Language understanding

The grounded runtime does not resolve customer language with Python word tables, string-pattern routing, or fuzzy entity matching. The LLM sees the active clinic catalog and selects canonical IDs from the records that actually exist in PostgreSQL.

Python validates every returned ID against the exact catalog snapshot before it may reach a tool. An invented ID is discarded and therefore cannot authorize or execute anything.

Legacy text-search helpers remain in the codebase only for the emergency rollback path when the unified interpreter is explicitly disabled. The default grounded runtime does not invoke them for customer entity resolution.

## Conversation state scope

The interpreter must explicitly select one scope on every turn:

- `flow`: this message continues/modifies/selects the active booking/reschedule flow, so persisted requirements may be inherited.

This prevents a question such as “what laser services do you have?” from accidentally inheriting a doctor, branch, date, or time from an earlier booking turn.

## Verified replies

Normal read/discovery replies are no longer customer-facing Python templates. The response composer receives only verified structured data from PostgreSQL/tool results and writes the natural customer reply.

It is forbidden to invent prices, durations, doctors, branches, dates, times, availability, or appointment state, and internal UUIDs must never be printed.

Booking/conflict/schedule calculation, write authorization, idempotency, appointment duration, overlap checks, and database constraints remain deterministic.

## Conversation flow policy

The existing persisted conversation-flow behavior is intentionally preserved. The grounded interpreter resolves canonical clinic IDs and generates customer-facing language, but it does not introduce a separate `context_scope` / `turn_only` state branch. Existing flow continuation, modification, interruption, option snapshots, and write authorization remain the source of truth for conversation state.
