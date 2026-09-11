# Agent Core V2

This package is an isolated, non-production implementation of Tia's next conversational core.

Current phases on this branch:

1. Small model-based semantic turn contract.
2. Ephemeral model-visible catalog references with deterministic server grounding.
3. Canonical booking/reschedule state and invalidation rules.
4. Deterministic planner and structured outcomes.

Architectural invariants:

- Customer-language interpretation is owned only by the structured semantic model.
- The planner/state layer never receives raw customer text.
- No keyword, regex, fuzzy, or lexical fallback is allowed for intent/entity/workflow semantics.
- Python owns business policy, write authorization, state invalidation, and verification.
- Database/clinic adapters remain final execution authorities.
- Customer-facing prose is not produced by planner/state code.
- Nothing in this package is wired into `agent_chat.py` yet.
