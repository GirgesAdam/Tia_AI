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
12. Isolated stateful V2 runtime coordinator that loads durable task state before interpretation, executes verified reads/state transitions, persists the final task once, and stops at a pending verified-write boundary instead of executing business writes.

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
- The stateful runtime coordinates existing semantic/planner/read/state/outcome layers; it does not own new language or business-policy rules.
- A stateful runtime turn persists the final changed booking/reschedule task at most once. Unchanged task state is not rewritten.
- A stale persistence handle or foreign-flow conflict propagates fail-closed; the runtime does not retry by overwriting newer state.
- A stateful runtime step that reaches `write_ready` becomes a `PendingV2Write`. It does not build a completed outcome, render a customer success reply, or execute the write.
- A shadow turn that reaches `write_ready` records only a write preview; it never executes the write or claims success.
- Shadow state-update turns do not persist V2 state.
- V1 remains the production path. Neither the stateful V2 runtime nor V2 persistence is wired into `agent_chat.py` or customer delivery yet.

Persistence contract:

`state_persistence.py` provides load/save/cancel/complete operations for `BookingTaskState` and `RescheduleTaskState` only. Save/update requires a `PersistedActiveTask` handle containing the flow id and expected database flow version. A stale version, malformed V2 payload, task/flow-type mismatch, or foreign active flow fails closed rather than silently replacing state.

The adapter deliberately uses the existing flow lifecycle and audit-event infrastructure for updates and terminal transitions, while V2 creation is create-only inside a savepoint so it cannot interrupt an existing foreign flow during a race.

Stateful runtime contract:

`orchestrator.py` is the isolated coordinator for one durable V2 turn. It loads persisted V2 task state before building the safe semantic state view, delegates customer-language interpretation to the structured interpreter, delegates policy to the deterministic planner, performs only the planner's verified reads and pure task-state transitions, and persists the final verified booking/reschedule task transition once at the end of the turn.

The runtime deliberately stops when a real business mutation is required. `write_ready` is returned as a pending verified write with no customer success reply. Booking, reschedule, appointment confirmation/cancellation, package purchase, follow-up, and marketing mutations remain unavailable until a separate real-write executor exists and returns verified action truth.

Migration boundary:

Durable state storage and an isolated stateful runtime coordinator now exist, but production orchestration is still intentionally absent. Before any production cutover, real V2 writes need an explicit executor with transactionally correct action results, and `agent_chat.py` needs a deliberate V2 entry boundary that owns the outer transaction, error handling, and customer delivery behavior.

Do not invoke the diagnostic shadow runtime inside V1's live database transaction merely to collect comparison data. Prefer an explicitly isolated diagnostic invocation or a separate-session/queue design before enabling automatic shadow execution.

Real V2 booking/reschedule/cancellation/package/follow-up/marketing write execution remains out of scope for this orchestration phase and must not be inferred from persisted task state alone.
