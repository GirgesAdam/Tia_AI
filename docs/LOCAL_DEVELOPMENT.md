# Local Development

Requirements: Python 3.12, Node.js 20+, Supabase/PostgreSQL, Supabase Auth, and a Gemini API key for AI-enabled flows.

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item ..\.env.example .env
alembic upgrade head
python -m uvicorn app.main:app --reload
```

Frontend: create `frontend/.env.local` with the Supabase public values and `TIA_API_URL`, then run:

```powershell
cd frontend
npm ci
npm run dev
```

Checks:

```powershell
# backend
ruff check app tests alembic
python -m compileall -q app alembic tests
python -m pytest -q

# frontend
npm run lint
npm run typecheck
```
