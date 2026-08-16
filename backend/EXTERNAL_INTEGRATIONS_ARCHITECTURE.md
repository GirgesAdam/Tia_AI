# Tia AI v0.18.0 — External Integration Architecture

## Boundary

Tia owns intent, policy, CRM state, booking state, handoffs, messages, dispatch
state and automation idempotency.

n8n owns external provider credentials and provider execution.

No Meta access token, Google OAuth token, Gmail password, or raw Tia adapter
credential is stored in `channel_connections.config`.

## Customer email capability

`email_communication` is a semantic capability. Python maps it to the
`send_email_to_customer` write tool.

The write tool has no `recipient` argument. It resolves the current patient's
saved email from CRM, selects the workspace's active/default `n8n_gmail`
connection, creates the email channel identity/conversation if needed, and
writes an outbound `Message` plus queued `MessageDispatch`.

Medical/human-support risk still collapses tool exposure to human handoff, so a
simultaneous medical request cannot use email as a route around safety policy.

## Delivery truth

Queued != sent != delivered/read.

Agent tool success means durable outbox persistence only. Provider results are
recorded by the adapter and remain the source of delivery-state transitions.

## Multi-tenant scope

Every adapter token resolves one channel connection and therefore one
workspace. Every automation worker token resolves one workspace. A workflow
using one of these credentials cannot claim another workspace's dispatches.

## No new migration

v0.18 reuses the existing channel connection, identity, conversation, message,
dispatch and automation worker tables. No database migration is required.
