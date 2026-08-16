# Tia AI Agent Foundation v0.6.1 — Groq-first

Tia AI now uses Groq by default during development while keeping OpenAI available as a later provider switch.

## Groq environment

Add these values to `backend/.env`:

```text
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=openai/gpt-oss-20b
LLM_TIMEOUT_SECONDS=45
LLM_MAX_RETRIES=2
AGENT_RECURSION_LIMIT=16
```

`OPENAI_API_KEY` is not required while `LLM_PROVIDER=groq`.

Keep all provider API keys server-side only.

## Install updated dependencies

From `backend/`:

```powershell
pip install -r requirements.txt
```

## Database

This provider-only patch has no new database migration.

If the previous Agent Foundation migration has already been applied, the expected head remains:

```text
0007_agent_foundation (head)
```

## Run

```powershell
uvicorn app.main:app --reload
```

Authenticated test endpoint:

```text
POST /api/v1/agent/chat
```

Required headers:

```text
Authorization: Bearer <SUPABASE_ACCESS_TOKEN>
X-Workspace-ID: <WORKSPACE_UUID>
```

Example body:

```json
{
  "patient_id": "<PATIENT_UUID>",
  "channel": "web",
  "message": "عايزة أحجز ليزر بكرة بعد الساعة 6"
}
```

## Provider switching later

To switch to OpenAI later, no agent/business-logic rewrite is needed. Change only environment variables:

```text
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.4-mini
```

## Egyptian Arabic behavior

The customer-service system prompt is unchanged:

- replies default to natural Egyptian Arabic;
- clinic facts and booking actions come from tools;
- the model cannot claim a booking succeeded until the database tool succeeds;
- medical/symptom/suitability questions are escalated to a human.
