# Analytics Production Validation Gate

Phase 7.7 closes the Analytics foundation with a read-only integrity gate. The gate is deliberately independent from the dashboard UI and re-runs the registered Analytics catalog against canonical database facts.

## What the gate validates

- Every registered catalog analysis executes with its materialized default request.
- Appointment totals reconcile independently against canonical `appointments` facts, excluding reschedule shells.
- Clinic-wide revenue reconciles independently against the immutable EGP payment ledger.
- Service-attributed revenue reconciles independently through explicit `payment_allocations -> appointments` joins only.
- Second/third-visit retention reconciles from canonical completed-visit counts per `patient_id`.
- Campaign delivery/read/failure facts reconcile from `message_dispatches`.
- Campaign bookings/revenue reconcile only from explicit `crm_campaign_conversions` and allocated EGP payment facts.
- Optional PostgreSQL `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` checks cover the representative heavy access patterns for retention, payment ledger, allocated revenue and campaign attribution.

The validation path performs no writes and does not use the Analytics aggregate cache.

## Run against staging / production-like PostgreSQL

From `backend`:

```powershell
python scripts\run_analytics_integrity_gate.py --workspace-slug tia --explain
```

The command exits `0` only when reconciliation passes and no representative query exceeds the default 1500 ms execution threshold. The threshold can be changed without changing product behavior:

```powershell
python scripts\run_analytics_integrity_gate.py --workspace-slug tia --explain --max-query-ms 2500
```

For a quick correctness-only pass, omit `--explain`.

## Release rule

A Phase 7+ release should not be treated as Analytics-safe if the integrity gate reports a reconciliation mismatch. Query-plan timing is environment/data-size dependent, so a slow plan should be investigated on the target PostgreSQL dataset rather than hidden by increasing application timeouts.
