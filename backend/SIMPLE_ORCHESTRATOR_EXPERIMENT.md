# Tia AI — Simple Orchestrator Experiment

This experiment tests a simpler customer-turn workflow without weakening write safety.

## Baseline

Fresh turn:

`Semantic Router -> policy -> prefetch -> optional customer agent -> tools -> response`

Active booking/reschedule flow:

`Flow Interpreter -> policy -> flow transition -> prefetch -> optional customer agent -> tools -> response`

The two semantic components overlap heavily and have historically created state-contract drift.

## Experimental path

With `AGENT_UNIFIED_TURN_INTERPRETER_ENABLED=true`:

`Unified Turn Interpreter -> deterministic policy/state -> deterministic prefetch/tools -> verified response or optional customer agent`

The interpreter returns one structured contract for both fresh and active-flow turns:

- capabilities and risks
- flow signal
- entity hints
- fields intentionally cleared
- option selection
- missing information
- handoff recommendation

It never returns tool names and cannot authorize writes.

## Safety kept unchanged

The experiment intentionally does **not** remove:

- persisted conversation flows
- optimistic version/CAS checks
- option snapshots
- deterministic capability policy
- write-tool isolation
- PostgreSQL validation and double-booking protection
- handoff policy

Those layers are safeguards, not routing complexity.

## What to compare

Use the same scenarios before/after enabling the flag and compare logs:

- `stage=semantic-router` / `stage=flow-interpreter` disappear
- `stage=unified-turn-interpreter` appears
- `total_duration_ms`
- correct preservation/clearing of service, branch, doctor, date, and time
- correct option selection across turns
- tool calls / prefetch behavior
- any 4xx/5xx process failures

The flag is off by default for immediate rollback.
