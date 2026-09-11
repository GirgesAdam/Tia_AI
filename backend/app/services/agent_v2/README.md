# Agent Core V2

This package is an isolated, non-production implementation of Tia's next conversational core.

Current phases on this branch:

1. Small model-based semantic turn contract.
2. Ephemeral model-visible catalog references with deterministic server grounding.
3. Canonical booking/reschedule state and dependency invalidation rules.
4. Pure deterministic active-task state executor for booking/reschedule progress across turns.
5. Deterministic planner and structured `TurnOutcome` contract.
6. Read-only executor over the existing clinic adapters and business read services.
7. Shared read-only package refund quoting with legacy/opening-balance safety checks.
8. Outcome builder that removes internal identifiers and prepares customer-visible verified facts.
9. One customer-facing V2 responder using native conversation roles and verified outcomes only.
10. Read-only shadow orchestrator for semantic/plan/read/outcome/reply comparison without writes or persistence.
11. Durable active-task persistence adapter over the existing conversation-flow tables, still isolated from production chat.

Architectural invariants:

- Customer-language interpretation is owned only by the structured semantic model.
- The planner/state/read policy layer never receives raw customer text.
- No keyword, regex, fuzzy, or lexical fallback is allowed for intent/entity/workflow semantics.
- Python owns business policy, write authorization, state invalidation, verification, and action truth.
- Database/clinic adapters remain final execution authorities.
- The responder owns customer-facing language but cannot call tools, execute actions, or mutate state.
- Canonical database identifiers are converted to ephemeral references before semantic-model input and removed before responder input.
- The pure state executor has no SQLAlchemy/database dependency. Durable storage is a separate adapter boundary.
- Persisted V2 state is namespaced under `entity_state.agent_core_v2` with an explicit schema version; non-V2 active flows are never decoded as V2 tasks.
- V2 reuses `conversation_flow_states` / `conversation_flow_events`; this persistence step adds no new database migration.
- Database `flow.version` is the optimistic-concurrency token for persistence. V2 `task.version` remains the deterministic domain-state version used for option invalidation/authorization semantics; the two versions are intentionally separate.
- Creating V2 state must fail closed when another active V1/foreign flow owns the conversation. The V2 persistence adapter does not call the generic `start_flow()` path that can interrupt a different active flow.
- Persistence mutations do not commit the transaction. The caller remains responsible for the outer transaction boundary.
- A shadow turn that reaches `write_ready` records only a write preview; it never executes the write or claims success.
- Shadow state-update turns do not persist V2 state.
- V1 remains the production path. V2 persistence is not wired into `agent_chat.py` or customer delivery yet.

Persistence contract:

`state_persistence.py` provides load/save/cancel/complete operations for `BookingTaskState` and `RescheduleTaskState` only. Save/update requires a `PersistedActiveTask` handle containing the flow id and expected database flow version. A stale version, malformed V2 payload, task/flow-type mismatch, or foreign active flow fails closed rather than silently replacing state.

The adapter deliberately uses the existing flow lifecycle and audit-event infrastructure for updates and terminal transitions, while V2 creation is create-only inside a savepoint so it cannot interrupt an existing foreign flow during a race.

Migration boundary:

Durable state storage now exists, but production orchestration is still intentionally absent. Before any production cutover, `agent_chat.py` needs an explicit V2 orchestration boundary that loads state before semantic interpretation, applies the pure state executor, persists only verified state transitions, and keeps real writes/action results transactionally correct.

Do not invoke the diagnostic shadow runtime inside V1's live database transaction merely to collect comparison data. Prefer an explicitly isolated diagnostic invocation or a separate-session/queue design before enabling automatic shadow execution.

Real V2 booking/reschedule/cancellation/package/follow-up/marketing write execution remains out of scope for this persistence phase and must not be inferred from persisted task state alone.
