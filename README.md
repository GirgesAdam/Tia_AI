# Tia AI

Tia AI is an AI-powered operations platform for aesthetic clinics. It brings patient operations, bookings, payments, packages, messaging, automations, analytics, and clinic onboarding into one workspace, with deterministic business rules behind AI-assisted workflows.

> Current application version: **0.49.0.15**

## What Tia does

- Clinic setup for branches, services, doctors, schedules, prices, and booking policies
- Patient CRM with notes, tags, conversations, and operational history
- Appointment booking and lifecycle management
- Payment ledger, allocations, refunds, and package accounting
- Historical data import with preview, validation, append/replace semantics, and provenance tracking
- Deterministic analytics and cohort/reporting workflows
- AI-assisted clinic operations with backend-enforced business rules
- External channel workflows through integrations and n8n workers
- Automation jobs, reminders, handoffs, and operational activity tracking
- Multi-tenant workspace authorization with Supabase Auth

## Architecture

```text
Next.js dashboard
       │
       ▼
FastAPI application ─────► Gemini / LangGraph
       │
       ▼
Supabase Auth + PostgreSQL
       │
       ▼
n8n / external integrations
```

The AI layer does not own financial, booking, package, identity, or authorization truth. Those rules are enforced by deterministic backend services and the database.

More detail: [Architecture](docs/ARCHITECTURE.md)

## Tech stack

**Frontend:** Next.js 16, React 19, TypeScript, Tailwind CSS, Supabase SSR/Auth  
**Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL/Supabase, LangGraph, Google Gemini  
**Automation:** n8n and durable channel/integration workers

## Repository structure

```text
backend/               FastAPI API, services, agents, models and migrations
frontend/              Next.js dashboard and onboarding UI
n8n/                   Automation/runtime workflow definitions and setup docs
docs/                  Architecture and development documentation
tools/                 Repository maintenance utilities
.github/workflows/     CI and controlled database migration workflows
.env.example           Environment variable reference
VERSION                Application version
```

## Local development

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item ..\.env.example .env
alembic upgrade head
python -m uvicorn app.main:app --reload
```

### Frontend

Create `frontend/.env.local`:

```text
NEXT_PUBLIC_SUPABASE_URL=https://PROJECT_REF.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_REPLACE_ME
TIA_API_URL=http://127.0.0.1:8000
```

Then:

```powershell
cd frontend
npm ci
npm run dev
```

See [Local development](docs/LOCAL_DEVELOPMENT.md).

## Database migrations

Current Alembic head:

```text
0052_payment_reference_constraint_repair
```

Production migrations should run through the protected GitHub Actions database migration workflow.

## Historical clinic data

Tia supports deterministic historical imports for patients, appointments, payments/refunds, packages, and explicit allocations. Patient identity uses stable identifiers and normalized phone rules rather than patient-name matching. Provenance links source records to canonical entities for safe append/replace behavior.

## Testing

Backend:

```powershell
cd backend
ruff check app tests alembic
python -m compileall -q app alembic tests
python -m pytest -q
```

Frontend:

```powershell
cd frontend
npm ci
npm run lint
npm run typecheck
```

Post-import reconciliation:

```powershell
cd backend
python scripts\run_post_import_smoke.py
```

## CI/CD

Pull requests and pushes to `main` run backend lint/compile/tests and frontend lint/type checking. Database migrations use a separate manually triggered workflow with GitHub environments for staging and production.

## Security

Never commit `.env`, `.env.local`, credentials, patient exports, database dumps, or clinic data. Supabase secret keys remain backend-only. See [SECURITY.md](SECURITY.md).

## Development workflow

Keep `main` deployable and use short-lived `feat/*`, `fix/*`, and `chore/*` branches. Use pull requests for business logic, migrations, integrations, or cross-module changes. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Proprietary. All rights reserved unless a separate license is added.
