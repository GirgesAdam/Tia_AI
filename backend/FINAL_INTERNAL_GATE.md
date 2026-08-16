# Tia AI v0.15.0 — Final Internal Gate

This milestone is a production-style internal gate, not another copy of the
full functional regression suite.

## Critical gates

1. True concurrent booking race
   - two requests hit the same doctor/slot concurrently
   - exactly one succeeds
   - PostgreSQL contains exactly one active appointment

2. Multi-tenant isolation
   - Workspace A cannot read or mutate Workspace B patient/appointment/conversation
   - Workspace B context cannot read Workspace A resources even with correct UUIDs

3. Real Member RBAC
   - creates a temporary, email-confirmed Supabase Auth user server-side
   - member in primary workspace
   - admin in deterministic secondary workspace
   - operational reads/writes allowed, including a real booking create
   - clinic/team/admin configuration denied in member context

4. Stateful workflow concurrency
   - optimistic version conflict is exercised with two database sessions
   - expired flow is closed and audit event is created

5. Automation lifecycle
   - reminder plan before reschedule
   - old reminder cancelled after reschedule
   - one replacement reminder planned
   - cancellation removes future reminder
   - disabled rule leaves no queued/failed jobs
   - stale processing job is reclaimable

6. Channel/handoff races
   - inbound persists while handoff is active
   - AI remains paused
   - no AI outbound dispatch is created
   - late failed/sent callbacks cannot downgrade `read`

7. Frontend Playwright E2E
   - real Supabase member login
   - patient search / booking view / setup RBAC
   - Team Inbox claim/reply/resolve when fixture remains active
   - workspace switching member -> admin -> member
   - real setup write in disposable secondary workspace
   - admin setup/team controls and a real automation toggle/restore

## Safety

The seed and runner refuse production.

All fixtures use deterministic IDs or a deterministic disposable secondary
workspace. The temporary Supabase Auth identity is created with a generated
password that is never printed. On a completely passing run, fixtures and the
ephemeral auth user are removed automatically unless `--keep-fixtures` is used.
On failure, fixtures are kept for inspection and the next seed resets them.

## Run

Backend unit contract:

`python -m pytest -q tests/test_final_internal_gate_contract.py`

Backend gate without browser E2E:

`python scripts/run_final_internal_gate.py`

Install browser once:

`cd ../frontend && npm install && npx playwright install chromium`

Then from backend run the complete gate:

`python scripts/run_final_internal_gate.py --frontend-e2e`

The Core should only be called internally stable when critical backend gates
and the browser E2E are all PASS.
