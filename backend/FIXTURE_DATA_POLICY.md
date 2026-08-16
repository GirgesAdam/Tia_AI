# Tia staging fixture data policy

Tia intentionally maintains two different fixture profiles.

## 1. Realistic E2E / Agent fixtures

Use the Final Internal Gate dataset for any new:

- frontend E2E scenario
- AI agent conversation
- onboarding scenario
- product demo-like staging check
- multi-step business workflow test

These fixtures use:

- plausible Arabic customer and clinic names
- Cairo / Africa-Cairo
- EGP pricing
- plausible service durations and appointment ranges
- explicit test markers
- no marketing consent
- `.example` email domains
- synthetic `+200000...` phone values that are structurally test-only

The data should look realistic in the UI while remaining unmistakably synthetic
at the contact/routing boundary.

## 2. Technical regression fixtures

The full staging regression dataset may retain deterministic technical labels
such as `Regression Cairo Branch` or scenario-specific patient names because
existing assertions use them.

Those labels are not the canonical UX demo data.

Technical regression fixtures must still obey safety rules:

- no real-looking routable customer phone numbers
- `.example` email domains
- deterministic workspace-scoped IDs
- explicit source/test markers
- staging only

## Stale database fixtures

Changing a seed file does not mutate rows that were created by an older seed
when a focused test deliberately avoids a full reset.

`normalize_staging_fixture_contacts.py` updates only contact fields on known
full-staging fixtures. It does not rename regression entities or rebuild
business objects, so it is safe to run before focused E2E work.

## Rule for future tests

New product-level tests should prefer the realistic Final Gate fixture profile.
Add technical scenario-specific fixtures only when an assertion genuinely needs
a deterministic technical label.
