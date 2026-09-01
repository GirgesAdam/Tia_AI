# v0.19.3.1 — Catalog & Prefetch Cleanup

This patch is intentionally limited to two issues found in the v0.19.3 runtime test.

## 1. Active clinic doctor catalog

A doctor is exposed to the LLM catalog only when the doctor is active/bookable and has:

- at least one active service assignment;
- at least one active branch assignment; and
- configured doctor working hours on one of those assigned active branches.

The staging realistic-clinic seed now also owns the fixture doctor set. When run without
`--keep-legacy-active`, Doctor records outside the seven deterministic fixture doctors are
removed from the fixture booking graph. Their Staff account is preserved unless it is an
explicit demo/regression staff record.

This is fixture/data cleanup, not customer-language routing.

## 2. Canonical-ID booking prefetch

In grounded mode, once the LLM has selected canonical `service_id`, `branch_id`, and
`doctor_id`, booking prefetch executes and reports only `get_booking_options`.

Legacy `search_services`, `list_branches`, and `list_doctors` coverage marking remains only
in the legacy non-grounded rollback path.

No keyword, regex, alias, or fuzzy entity routing was added. Conversation Flow is unchanged.
