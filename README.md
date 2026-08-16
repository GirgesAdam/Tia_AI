# Tia AI

Tia AI is a production-first AI operating system for aesthetic clinics.

Current backend version: **0.3.1**

## Current foundation

The backend currently includes:

- FastAPI
- SQLAlchemy 2
- Alembic migrations
- Supabase managed PostgreSQL
- Supabase Auth
- Multi-tenant workspaces
- Workspace roles: `admin`, `member`
- Clinic Core: branches, staff, doctors, services, working hours, booking settings
- Database-backed health checks
- GitHub Actions CI and protected migration workflow

## Authentication architecture

The frontend authenticates users with Supabase Auth and sends the Supabase access token to FastAPI:

```text
Authorization: Bearer <supabase_access_token>
```

Workspace-scoped requests also send:

```text
X-Workspace-ID: <workspace_uuid>
```

FastAPI verifies the Supabase access token and then checks the authenticated user's active membership in the requested workspace.

### Roles

- `admin`: full Clinic Core read/write access and workspace member management.
- `member`: read-only Clinic Core access.

Admins can invite either admins or members, change workspace roles, and remove workspace members.

Tia AI prevents changing or removing the last active admin in a workspace, so a clinic cannot accidentally lock itself out of administration.

## Supabase keys

Use:

- `sb_publishable_...` for user-token verification/client operations.
- `sb_secret_...` only in the trusted FastAPI backend.

Never expose the secret key in the frontend.

## Database access policy

Tia AI currently uses FastAPI as the only application data gateway.

Migration `0003_auth_rbac` enables PostgreSQL Row Level Security on the application tables and revokes direct Data API privileges from the `anon` and `authenticated` Postgres roles. This prevents a browser client from bypassing FastAPI workspace authorization.

Migration `0004_admin_member_roles` reduces the workspace role model to `admin` and `member`. If a database already passed through the earlier role model, legacy elevated memberships are converted to `admin` automatically before the stricter check constraint is applied.

The backend connects directly to managed PostgreSQL and performs tenant authorization before every workspace-scoped query.

## Environment

Copy the environment template:

```powershell
Copy-Item ..\.env.example .env
```

Configure:

```text
DATABASE_URL=...
MIGRATION_DATABASE_URL=...
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
SUPABASE_SECRET_KEY=sb_secret_...
CORS_ORIGINS=https://your-frontend.example.com
```

Use staging credentials in the staging environment and production credentials only in the protected production environment.

## Install

From `backend/`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Apply migrations

```powershell
alembic upgrade head
alembic current
```

Expected current head:

```text
0004_admin_member_roles (head)
```

## Create the Tia workspace

If it does not already exist:

```powershell
python scripts/provision_workspace.py --name "Tia" --slug tia
```

## Bootstrap the first admin

1. In Supabase, create the first real admin user under **Authentication > Users**.
2. Copy that user's UUID.
3. Run:

```powershell
python scripts/bootstrap_admin.py `
  --workspace-slug tia `
  --auth-user-id "SUPABASE_AUTH_USER_UUID" `
  --email "admin@example.com" `
  --full-name "Tia Admin"
```

This links the Supabase Auth identity to the internal Tia AI user and creates an `admin` workspace membership.

## Run

```powershell
uvicorn app.main:app --reload
```

Health endpoints:

```text
GET /api/v1/health/live
GET /api/v1/health/ready
```

Auth endpoints:

```text
GET    /api/v1/auth/me
GET    /api/v1/auth/workspace
GET    /api/v1/auth/workspace/members
POST   /api/v1/auth/workspace/invitations
PATCH  /api/v1/auth/workspace/members/{membership_id}
DELETE /api/v1/auth/workspace/members/{membership_id}
```

Clinic endpoints remain under:

```text
/api/v1/clinic/...
```

Clinic read requests require an active `admin` or `member` membership. Clinic writes require `admin`.

## GitHub environments

Create GitHub environments:

- `staging`
- `production`

Add these secrets to each environment:

```text
MIGRATION_DATABASE_URL
SUPABASE_URL
SUPABASE_PUBLISHABLE_KEY
SUPABASE_SECRET_KEY
```

Use the corresponding staging or production Supabase project values.

## Migration history

```text
0001_foundation
      ↓
0002_clinic_core
      ↓
0003_auth_rbac
      ↓
0004_admin_member_roles
```

## Next milestone

The next backend milestone is the CRM foundation:

- patients
- leads
- patient notes
- patient tags
- conversations
- messages
- source attribution
- patient identity matching

This becomes the memory layer that the future Tia AI agent will use before the booking engine and messaging automations are connected.
