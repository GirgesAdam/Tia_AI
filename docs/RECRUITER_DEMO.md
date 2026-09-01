# Tia Recruiter / Admin Demo

This environment is intentionally separate from development and real clinic data.
The demo uses the real Tia agent, booking engine, authorization layer, and database
writes while provider delivery is disabled.

## Recommended topology

- Frontend: Vercel (`frontend/`)
- Backend: Railway (`backend/`)
- Database/Auth: a dedicated Supabase project
- AI: Gemini key with an explicit usage budget

Do not point the public demo at a development or customer Supabase project.

## Backend environment

```env
ENVIRONMENT=demo
DEMO_MODE=true
DEMO_ALLOW_EXTERNAL_DISPATCH=false
DEMO_AGENT_HOURLY_TURN_LIMIT=60
CORS_ORIGINS=https://YOUR_DEMO_FRONTEND
```

Configure the normal database, Supabase and Gemini variables as well.

## Frontend environment

```env
TIA_API_URL=https://YOUR_DEMO_API
NEXT_PUBLIC_SUPABASE_URL=https://YOUR_DEMO_PROJECT.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...

TIA_DEMO_ENABLED=true
NEXT_PUBLIC_TIA_DEMO_ENABLED=true
TIA_DEMO_EMAIL=demo@YOUR_DOMAIN
TIA_DEMO_PASSWORD=STRONG_DEMO_PASSWORD
```

`TIA_DEMO_EMAIL` and `TIA_DEMO_PASSWORD` are server-only. They are used by the
"Try Admin Demo" server action and are never embedded in browser JavaScript.

## Prepare the database

Run migrations first:

```bash
cd backend
alembic upgrade head
```

Then seed the isolated demo workspace:

```bash
python scripts/seed_recruiter_demo.py
```

The seed creates realistic clinic configuration and three recruiter-friendly customer personas:

1. `مريم تجربة الحجز` — clean customer for new-booking tests.
2. `نور تجربة التعديل` — has an upcoming appointment for reschedule/cancel tests.
3. `سارة تجربة السجل` — has completed appointment history.

## Create the demo admin

Create one Auth user in the demo Supabase project using the same email/password
configured in the frontend environment. Copy its Auth user UUID, then attach it to
Tia as an admin:

```bash
python scripts/bootstrap_admin.py \
  --workspace-slug tia-demo \
  --auth-user-id AUTH_USER_UUID \
  --email demo@YOUR_DOMAIN \
  --full-name "Tia Demo Admin"
```

## What a recruiter can test

From `/agent-demo`, the recruiter can select a demo customer and send natural-language
messages to the real customer agent. Useful scenarios include:

- book a service based on real availability;
- ask for upcoming appointments;
- reschedule an existing appointment;
- cancel an appointment;
- verify the result in Appointments and the Patient timeline.

These operations persist to the demo PostgreSQL database. The sandbox does not claim
queued outbound messages for WhatsApp, email, or other providers while
`DEMO_ALLOW_EXTERNAL_DISPATCH=false`.

## Cost control

The public `/agent/chat` path is bounded by `DEMO_AGENT_HOURLY_TURN_LIMIT` while
`DEMO_MODE=true`. Also configure a provider-side Gemini budget/quota for the demo key.

## Reset strategy

For a public portfolio demo, reset the Supabase demo project periodically or run a
controlled cleanup + seed job. Never use the recruiter environment as a source of
business truth.
