# Phase 2 — Clinic Integration Architecture

## Goal

Decouple Tia's agent from the storage/schema used by a clinic without changing
customer-facing behavior or weakening booking safety.

## Implemented boundaries

### 1. Canonical clinic catalog

```text
Agent semantic layer
        |
        v
build_clinic_catalog()
        |
        v
get_clinic_adapter(workspace)
        |
        +--> TiaDatabaseClinicAdapter (current default)
        |        |
        |        +--> PostgreSQL / SQLAlchemy models
        |
        +--> Future clinic API / spreadsheet-backed / custom adapter
```

`app/agents/clinic_grounding.py` no longer imports Service, Branch, Doctor,
DoctorService, DoctorBranch, Staff, or working-hours ORM models. It consumes the
canonical catalog returned by the adapter.

### 2. Canonical availability

Availability reads now cross the same adapter boundary:

```text
get_booking_options() / get_available_slots()
                |
                v
       ClinicAdapter.get_availability()
                |
      +---------+----------+
      |                    |
      v                    v
TiaDatabaseAdapter   Future clinic adapter
      |                    |
      v                    v
existing booking      clinic API / imported
engine + PostgreSQL   scheduling source
```

The native adapter still calls the existing `calculate_availability()` booking
engine. The scheduling algorithm was not rewritten; only ownership of the call
moved behind the integration boundary.

### 3. Canonical patient appointment reads

The customer-facing appointment list now crosses the adapter boundary too:

```text
get_customer_appointments()
          |
          v
ClinicAdapter.get_patient_appointments()
          |
   +------+-------+
   |              |
   v              v
TiaDatabase   Future clinic
Adapter       adapter
   |              |
   v              v
joined native   API/imported
appointment     appointment
query           source
```

The canonical appointment record carries source-agnostic appointment/patient/
service/branch/doctor IDs, display labels, status, absolute start/end times,
timezone, and price. The agent no longer needs ORM lookups to render a patient's
appointment list.

The native adapter deliberately uses one joined read instead of the previous
per-appointment service/branch/doctor lookups, removing the N+1 query pattern
from this customer-facing list path.

Reschedule discovery now consumes these same canonical appointment records, so
it no longer queries the native `Appointment` table from the agent-tool layer.


### 4. Canonical appointment lifecycle writes

Create, confirm, cancel, and reschedule now cross the adapter boundary:

```text
book / confirm / cancel / reschedule tool
                  |
                  v
          ClinicAdapter mutation DTO
                  |
          +-------+--------+
          |                |
          v                v
TiaDatabaseAdapter   Future clinic adapter
          |                |
          v                v
native appointment   clinic API / PMS /
write + history      external source
```

Canonical mutation requests use string IDs and an `operation_id` so external
systems can use their own identifiers and idempotency keys. The result is a
canonical `AppointmentRecord`, so response formatting never needs native ORM
objects.

For the native adapter, existing booking safety is preserved rather than
rewritten:

- exact slots are revalidated with the existing `find_exact_slot()` engine;
- booking confirmation settings still decide `pending` vs `confirmed`;
- cancellation notice rules are still enforced;
- rescheduling still excludes the old appointment while validating the new slot;
- PostgreSQL overlap protection remains unchanged;
- native `appointment_status_history` rows are still written for every lifecycle
  transition;
- lead-to-booked updates still happen on appointment creation.

The native adapter intentionally performs mutation + `flush()` without committing.
The agent tool then adds Tia's `AgentAction` audit record and commits once. This
keeps the native appointment mutation, native status history, and agent audit in
one PostgreSQL transaction. An external adapter may commit to its own source
system, while Tia still records the operational `AgentAction` separately.

Cancellation policy can return `ClinicActionRequiresHuman`; the Tia tool maps
that source decision to conversation handoff state instead of embedding handoff
logic inside the clinic adapter.

`AgentAction.appointment_id` remains a nullable native UUID foreign key. When an
external adapter returns a non-UUID appointment ID such as `BOOKING-443`, the ID
stays in the action payload and the native FK is left empty rather than coercing
or losing the external identifier.

## Capabilities

Each adapter declares what the connected clinic system can safely support:

- `catalog.read`
- `availability.read`
- `appointments.read`
- `appointments.create`
- `appointments.confirm`
- `appointments.cancel`
- `appointments.reschedule`

This is important for incomplete integrations. For example, an imported Excel
file may expose doctors/services but have no trustworthy schedules. Such an
adapter can support `catalog.read` while rejecting `availability.read` rather
than letting the agent guess missing data.

## Source-agnostic IDs

Canonical integration DTOs use string IDs deliberately. Tia's native adapter
converts UUID strings to PostgreSQL keys, while an external system may use IDs
such as `DR-17`, `BRANCH-TAGAMO3`, or an imported row key. The agent contract does
not need to change when the source system changes.

## Availability contract

`AvailabilityRequest` contains canonical IDs, date, optional doctor, and an
optional appointment exclusion for rescheduling.

`AvailabilityResult` returns:

- source timezone
- canonical branch/service identity and display labels
- service duration/base price when available
- verified canonical slots
- doctor display labels per slot

This keeps provider-specific DB/API lookups out of the response formatting path.

## Workspace integration configuration

Each workspace now has one `clinic_integrations` row keyed by `workspace_id`.
Supported integration modes are:

- `tia_native` — Tia PostgreSQL is the live clinic source of truth.
- `external_api` — an external PMS/clinic API will own live data.
- `hybrid` — responsibilities can be split between Tia and an external system.
- `imported` — external files are imported/normalized into Tia, then the native adapter runs them.

The row also stores `adapter_key`, lifecycle `status`, optional
`external_clinic_id`, non-secret provider config, and a `secret_ref`. Plain
configuration rejects credential-like keys; actual API keys/tokens/passwords
must live outside the row in a secret manager.

Adapter resolution is fail-closed. A workspace configured for a paused,
setup-required, or unavailable external adapter never silently falls back to
Tia's local booking tables. Existing workspaces are backfilled as
`tia_native + tia_database + active`, preserving current behavior. Newly created
workspaces persist the same native integration row in the onboarding transaction.

`clinic_integration_entity_links` stores one-to-one mappings between canonical
Tia IDs and external source IDs for services, branches, doctors, patients, and
appointments. This prepares hybrid/external adapters for IDs such as `DR-17`,
`BOOKING-443`, or spreadsheet-derived keys without changing the agent contract.

Because `workspace_id` is the integration table primary key, the resolver uses
`Session.get()` and can reuse SQLAlchemy's identity map when the adapter is
resolved multiple times during one request. Catalog cache signatures also include
the adapter namespace so switching source systems cannot reuse a catalog cached
for a different adapter.

## Current adapter

`TiaDatabaseClinicAdapter` preserves existing Tia behavior. It owns native
SQLAlchemy queries, calls the existing booking engine, and maps results to the
canonical DTOs.

It also exposes `catalog_revision()` so catalog caching remains freshness-guarded.

## Remaining migration sequence

1. **Catalog boundary** — implemented.
2. **Capabilities + availability boundary** — implemented.
3. **Appointment read boundary** — implemented, including reschedule discovery.
4. **Appointment lifecycle/write boundary** — implemented for create/confirm/cancel/reschedule.
5. **Workspace integration configuration + external-ID links** — implemented.
6. **External adapter prototype** — prove the contract against a non-Tia API/data shape.
7. **Connector + mapping/import layer** — Excel/CSV/Google Sheets/API discovery, normalization, missing-data validation, and sync/import state.
8. **Secret-manager/provider credential wiring** — resolve `secret_ref` without storing secrets in workspace config.

The semantic interpreter, policy layer, conversation flow, handoff layer, and
response composer should not need vendor-specific branching.
