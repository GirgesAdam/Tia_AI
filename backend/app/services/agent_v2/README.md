# Agent Core V2

This package is an isolated, non-production implementation of Tia's next conversational core.

Current phases on this branch:

1. Small model-based semantic turn contract.
2. Ephemeral model-visible catalog references with deterministic server grounding.
3. Canonical booking/reschedule state and dependency invalidation rules.
4. Deterministic planner and structured `TurnOutcome` contract.
5. Read-only executor over the existing clinic adapters and business read services.
6. Shared read-only package refund quoting with legacy/opening-balance safety checks.
7. Outcome builder that removes internal identifiers and prepares customer-visible verified facts.
8. One customer-facing V2 responder using native conversation roles and verified outcomes only.
9. Read-only shadow orchestrator for semantic/plan/read/outcome/reply comparison without writes or persistence.

Architectural invariants:

- Customer-language interpretation is owned only by the structured semantic model.
- The planner/state/read policy layer never receives raw customer text.
- No keyword, regex, fuzzy, or lexical fallback is allowed for intent/entity/workflow semantics.
- Python owns business policy, write authorization, state invalidation, verification, and action truth.
- Database/clinic adapters remain final execution authorities.
- The responder owns customer-facing language but cannot call tools, execute actions, or mutate state.
- Canonical database identifiers are converted to ephemeral references before semantic-model input and removed before responder input.
- A shadow turn that reaches `write_ready` records only a write preview; it never executes the write or claims success.
- Shadow state-update turns do not persist V2 state.
- V1 remains the production path. Nothing here is wired into `agent_chat.py` or customer delivery yet.

Migration boundary:

The next production-facing step must preserve transaction isolation. Do not invoke the shadow runtime inside V1's live database transaction merely to collect comparison data. Prefer an explicitly isolated diagnostic invocation or a separate-session/queue design before enabling automatic shadow execution.
