# Tia AI

> AI-powered operating platform for aesthetic clinics — built to connect patient communication, booking, clinic operations, payments, CRM, analytics, and automation in one system.

Tia AI is an intelligent clinic operations platform designed for aesthetic and cosmetic clinics.

Instead of operating as a standalone chatbot, Tia is designed as an **AI agent connected to the clinic's operational data and workflows**. It can understand patient requests, interact with clinic systems, execute approved actions, and provide administrators with a unified view of clinic activity.

The platform combines an AI orchestration layer with deterministic business services for workflows where correctness matters — including scheduling, payments, packages, patient identity, historical data, and analytics.

---

## Overview

A modern aesthetic clinic typically operates across several disconnected systems:

* Patient conversations
* Appointment scheduling
* Doctors and availability
* Services and pricing
* Payments
* Treatment packages
* CRM and follow-ups
* Marketing campaigns
* Historical patient records
* Reporting and analytics
* External communication channels

Tia brings these workflows into a single operational layer.

The AI agent provides the conversational interface, while the backend remains the source of truth for business rules and transactional operations.

```text
Patient / Clinic Admin
        │
        ▼
Communication Channels
        │
        ▼
┌─────────────────────────┐
│       Tia AI Agent      │
│                        │
│ Intent & orchestration │
│ Tool selection         │
│ Context                │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Deterministic Services  │
│                        │
│ Booking                │
│ Patients               │
│ Payments               │
│ Packages               │
│ CRM                    │
│ Analytics              │
│ Automations            │
└────────────┬────────────┘
             │
             ▼
     Canonical Clinic Data
```

The core principle is simple:

**AI decides what capability is needed. Deterministic backend services decide what is actually valid.**

---

# Core Capabilities

## AI Clinic Agent

Tia provides an AI layer capable of understanding natural-language requests and interacting with clinic capabilities.

Rather than relying on keyword or regex routing, the system is designed around semantic intent understanding and explicit backend tools.

The agent can work with capabilities such as:

* Appointment discovery
* Booking
* Rescheduling
* Cancellation
* Patient lookup
* Service information
* Doctor information
* Clinic information
* Payment workflows
* Package information
* CRM operations
* Operational actions
* Administrative workflows

The language model is not treated as the source of truth for clinic operations.

For sensitive operations, the AI calls deterministic backend services that validate the request against canonical clinic data.

---

# Patient Management

Tia maintains a canonical patient model shared across clinic workflows.

Patient information can originate from:

* Historical clinic imports
* New bookings
* Conversations
* CRM workflows
* External integrations
* Administrative actions

### Patient Identity Resolution

Patient identity is handled conservatively.

Historical imports resolve identity using:

```text
patient_id
OR
normalized phone number
```

Patient names are **not used as a merge key**.

This avoids dangerous situations where two patients with similar names are accidentally merged.

Phone numbers are normalized before identity resolution.

If a historical patient already exists, new imports can safely enrich missing patient information without destructively overwriting established canonical data.

---

# Appointment & Booking Engine

Booking is implemented as a deterministic backend capability.

The AI does not invent availability.

Availability is calculated using actual clinic configuration including:

* Clinic working hours
* Doctor working hours
* Doctor/service relationships
* Doctor branches
* Appointment duration
* Existing appointments
* Visiting doctor availability
* Booking policies
* Minimum booking notice
* Booking horizon
* Same-day booking rules

The engine supports appointment lifecycle states such as:

```text
pending
confirmed
checked_in
in_progress
completed
cancelled
no_show
rescheduled
```

### No-show behavior

For package accounting purposes:

```text
no_show ≈ cancelled
```

A no-show does not consume a package session.

---

# Doctor Management

Tia supports two main doctor models.

## Regular Doctors

Regular doctors use recurring weekly schedules.

Example:

```text
Monday     10:00 → 18:00
Wednesday  12:00 → 20:00
Saturday   10:00 → 16:00
```

## Visiting Doctors

Visiting doctors use explicit dated availability windows instead of permanent weekly schedules.

Example:

```text
2026-09-10  14:00 → 20:00
2026-09-17  14:00 → 20:00
```

This supports specialists who visit the clinic periodically.

Historical doctors discovered during data import can also be represented without automatically making them bookable.

---

# Services

Clinic services are represented using a simple operational model:

```text
Name
Category
Duration
Price
```

Example:

```text
Full Body Laser
Category: Laser
Duration: 60 minutes
Price: 2500 EGP
```

Services are linked to doctors so availability can be calculated based on who is actually allowed to perform a treatment.

---

# Clinic Setup

Tia includes a structured clinic onboarding flow.

The administrator can configure:

* Clinic profile
* Services
* Doctors
* Doctor/service relationships
* Clinic working hours
* Doctor working hours
* Visiting doctor windows
* Booking policies

Configuration can be entered manually or loaded from an Excel workbook.

---

## Excel-Based Clinic Setup

Tia supports a structured setup workbook containing sheets such as:

```text
clinic_profile
services
doctors
doctor_services
clinic_hours
doctor_hours
visiting_windows
booking_policy
```

The import process follows a preview-first workflow.

```text
Upload workbook
      ↓
Parse & validate
      ↓
Preview proposed configuration
      ↓
Admin reviews / edits
      ↓
Save clinic configuration
```

Missing workbook values are not silently replaced with fabricated defaults.

The administrator remains in control of the final clinic configuration.

---

# Historical Data Import

Existing clinics rarely start with an empty database.

They may already have years of:

* Patients
* Appointments
* Payments
* Packages
* Treatment history

Tia therefore includes a historical import pipeline designed to migrate existing clinic data into its canonical model.

Supported historical entities include:

```text
Patients
Appointments
Payments
Packages
Payment allocations
```

---

## Flexible Historical Data Structures

Clinic data is rarely organized consistently.

Different systems may represent the same information using:

* Different column names
* Different tables
* Combined tables
* Separate exports
* Different identifiers
* Different payment structures
* Different appointment structures

Tia's import architecture separates external data interpretation from canonical storage.

```text
External clinic data
        ↓
Interpretation / normalization
        ↓
Validation
        ↓
Canonical entities
        ↓
Historical provenance
        ↓
Runtime clinic database
```

---

## Preview Before Import

Historical imports are inspected before being committed.

The administrator can see counts such as:

```text
Patients       50
Appointments  100
Payments       34
Packages       10
```

Invalid rows can be isolated rather than causing the entire import to fail unnecessarily.

---

## Append vs Replace

Historical imports support controlled update semantics.

### Append

Used when importing additional historical data.

Existing immutable historical facts are protected from silent modification.

### Replace Previous Imports

Used when a previously imported source needs to be replaced.

Replacement is constrained to records owned by the historical import system.

Runtime activity created later by Tia is protected from destructive replacement.

---

## Import Provenance

Imported records retain provenance information connecting the source record to the canonical entity.

This enables Tia to reason about:

* Which batch created a record
* Whether the same source was imported previously
* Whether a source record changed
* Whether replacing previous imported data is safe

---

# Payments

Tia includes a payment ledger rather than treating payments as arbitrary appointment fields.

Payment transactions can represent:

```text
payment
refund
```

Payment methods include concepts such as:

```text
cash
card
bank_transfer
wallet
online
other
unknown
```

Historical imports infer transaction direction from the amount:

```text
positive amount → payment
negative amount → refund
```

The system does not invent missing refund references during historical migration.

---

# Payment Allocations

Payments can be allocated to appointments explicitly.

This separates:

```text
Money received
```

from:

```text
What the money paid for
```

That distinction enables more reliable financial reporting and package accounting.

Historical allocations are not guessed when the source data does not contain enough evidence.

---

# Treatment Packages

Tia supports treatment packages in addition to standalone sessions.

A package can track concepts such as:

* Patient
* Service
* Number of sessions
* Remaining sessions
* Package price
* Payment state
* Usage

Package usage is linked to operational appointment activity.

---

# Package Refund Logic

Package refunds use deterministic accounting rules.

Consider a patient purchasing a discounted package.

If the patient uses part of the package and then requests a refund, the consumed sessions are repriced using the normal standalone session price.

Example:

```text
Full package paid:       8,000 EGP

Standalone session:      2,500 EGP

Sessions consumed:       1
                         ─────────
Consumed value:          2,500 EGP

Refund:                   5,500 EGP
```

The customer therefore loses the unused portion of the package discount when refunding the package.

This calculation is handled by backend business logic rather than language-model reasoning.

---

# CRM

Tia contains CRM capabilities for managing patient relationships beyond individual bookings.

The platform includes concepts such as:

* Leads
* CRM tasks
* Cohorts
* Cohort members
* Patient notes
* Patient tags
* Follow-up workflows

This allows the clinic to move from reactive booking management toward structured patient lifecycle management.

---

# Conversations

Tia maintains conversation state rather than treating every message independently.

Conversation infrastructure includes:

* Conversations
* Messages
* Channel identities
* Inbound events
* Delivery events
* Dispatches
* Conversation flow state
* Conversation flow events
* Handoff requests
* Handoff events

This provides a foundation for persistent AI-assisted patient communication.

---

# Human Handoff

AI automation should not force every conversation through an autonomous workflow.

Tia supports handoff concepts that allow conversations or operational cases to move to human staff when appropriate.

This is particularly important for:

* Sensitive requests
* Ambiguous cases
* Operational exceptions
* Patient complaints
* Situations requiring clinic judgment

---

# Automation Engine

Tia includes an automation layer for operational workflows.

Examples include:

* Appointment reminders
* Follow-up tasks
* Scheduled actions
* CRM workflows
* Communication workflows

The architecture includes:

```text
Automation Rules
Automation Jobs
Automation Workers
```

Jobs are tied to concrete operational targets instead of existing as unstructured background prompts.

---

# Analytics

Tia includes an analytics layer built on canonical clinic data.

A major design decision is that business metrics are calculated using deterministic backend functions rather than asking an LLM to estimate results from raw records.

The AI may help the administrator select or explain an analysis, but the numbers themselves come from deterministic queries.

Analytics can cover areas such as:

* Appointment activity
* Patient activity
* Service performance
* Doctor performance
* Revenue
* Payment activity
* Package activity
* Operational trends
* CRM cohorts
* Conversion-related metrics

The platform also supports saved analytics views.

---

# AI-Assisted Clinic Administration

Tia is designed not only for patients but also for clinic administrators.

Administrative workflows can combine natural-language interaction with structured actions.

The long-term operating model is:

```text
Admin request
      ↓
AI understands intent
      ↓
AI prepares an explicit operation
      ↓
Deterministic validation
      ↓
Admin approval when required
      ↓
Canonical data mutation
      ↓
Audit / activity record
```

This keeps the conversational flexibility of AI without allowing the model to directly become the database business layer.

---

# Integrations

Tia is designed to connect with external systems rather than operate as an isolated demo.

The architecture includes clinic integration entities and synchronization infrastructure.

Integration-related capabilities include:

* External entity mapping
* Synchronization schedules
* Channel connections
* Communication delivery
* External workflow automation

The project also incorporates **n8n** as part of its automation and integration architecture.

n8n can be used to orchestrate external workflows and services while Tia remains responsible for clinic-domain logic.

---

# Gmail & Communication Workflows

The broader integration architecture supports communication-oriented workflows such as email and external messaging.

The goal is for the agent to execute real operations through integrations when authorized rather than simply replying that an action was completed.

---

# Operational Safety

Tia separates generative reasoning from transactional correctness.

Critical operations are implemented in deterministic services.

Examples include:

```text
Availability calculation
Patient identity
Payment accounting
Package consumption
Refund calculations
Historical import
Analytics calculations
Data replacement rules
```

This reduces the risk of hallucinated business state.

---

# Architecture

Tia is organized as a full-stack application.

```text
┌─────────────────────────────────────────────┐
│                 Frontend                    │
│              Next.js / React                │
└─────────────────────┬───────────────────────┘
                      │
                      │ HTTP API
                      ▼
┌─────────────────────────────────────────────┐
│                  Backend                    │
│                  FastAPI                    │
│                                             │
│  API Routes                                 │
│       │                                     │
│       ├── Agent orchestration               │
│       ├── Booking services                  │
│       ├── Patient services                  │
│       ├── Payments                          │
│       ├── Packages                          │
│       ├── Historical import                 │
│       ├── CRM                               │
│       ├── Analytics                         │
│       └── Automation                        │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│             PostgreSQL / Supabase           │
│                                             │
│          Canonical clinic data              │
└─────────────────────────────────────────────┘

External systems
      │
      ├── AI model providers
      ├── Communication channels
      ├── Gmail
      ├── n8n
      └── Clinic integrations
```

---

# Technology Stack

## Backend

* Python
* FastAPI
* SQLAlchemy
* Alembic
* PostgreSQL
* Pydantic

## Frontend

* Next.js
* React
* TypeScript

## Data & Authentication

* Supabase
* PostgreSQL

## AI

* LLM-based agent orchestration
* Structured tool calling
* Deterministic clinic-domain capabilities

## Automation & Integrations

* n8n
* External communication adapters
* Integration synchronization infrastructure

## Testing

* pytest
* Backend regression suites
* Frontend linting
* TypeScript type checking
* CI quality gates

---

# Repository Structure

```text
tia-ai/
│
├── backend/
│   ├── alembic/
│   │   └── versions/
│   │
│   ├── app/
│   │   ├── agents/
│   │   ├── api/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── ...
│   │
│   ├── scripts/
│   ├── tests/
│   └── ...
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── ...
│
├── docs/
│
├── n8n/
│
├── tools/
│
├── .github/
│   └── workflows/
│
├── .env.example
├── CONTRIBUTING.md
├── SECURITY.md
├── VERSION
└── README.md
```

---

# Local Development

## Requirements

Recommended local dependencies:

```text
Python 3.11+
Node.js
npm
PostgreSQL / Supabase project
```

---

## Clone

```bash
git clone <repository-url>
cd tia-ai
```

---

## Environment

Copy the example environment file and configure your local credentials.

Never commit real secrets.

Typical configuration includes:

```env
DATABASE_URL=
SUPABASE_URL=
SUPABASE_KEY=

GEMINI_API_KEY=

NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=
TIA_API_URL=http://127.0.0.1:8000
```

Refer to `.env.example` for the current configuration contract.

---

## Backend

```bash
cd backend

python -m venv .venv
```

Activate the environment.

Windows:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run database migrations:

```bash
alembic upgrade head
```

Start the API:

```bash
python -m uvicorn app.main:app --reload
```

The development API is normally available at:

```text
http://127.0.0.1:8000
```

FastAPI documentation:

```text
http://127.0.0.1:8000/docs
```

---

# Frontend

```bash
cd frontend

npm install
npm run dev
```

Configure:

```env
TIA_API_URL=http://127.0.0.1:8000
```

along with the required Supabase public configuration.

---

# Database Migrations

Database schema changes are managed with Alembic.

Apply the latest schema using:

```bash
cd backend
alembic upgrade head
```

Never manually mark a migration as complete unless the database state has been explicitly verified.

---

# Testing

## Backend

```bash
cd backend
pytest
```

Individual suites can also be executed during development.

Example:

```bash
pytest tests/test_payment_ledger_phase57.py -q
```

---

## Frontend

```bash
cd frontend

npm run lint
npm run typecheck
```

---

# Post-Import Verification

Tia includes operational verification tooling for validating a historical import against canonical runtime data.

After importing clinic data:

```bash
cd backend
python scripts/run_post_import_smoke.py
```

The smoke gate verifies areas such as:

```text
Historical batches
Provenance
Patients
Appointments
Relationships
Payments
Refunds
Packages
Analytics
```

This provides an additional integrity check before using imported data operationally.

---

# Development Workflow

The repository follows a branch-based development workflow.

Create a branch:

```bash
git checkout -b fix/example-change
```

Commit using descriptive messages:

```bash
git add .
git commit -m "fix: correct example behavior"
```

Push:

```bash
git push -u origin fix/example-change
```

Then open a Pull Request into:

```text
main
```

Recommended commit prefixes:

```text
feat:
fix:
refactor:
test:
docs:
chore:
```

---

# CI

GitHub Actions provides automated quality checks for both backend and frontend changes.

Typical checks include:

```text
Backend tests
Python validation
Frontend lint
TypeScript type checking
```

Critical changes should not be merged until the relevant CI checks pass.

---

# Security

Real credentials must never be committed to the repository.

This includes:

* Database credentials
* Supabase secrets
* AI provider API keys
* Gmail credentials
* OAuth credentials
* n8n secrets
* Webhook secrets
* Production tokens
* Patient exports

Use environment variables and secret-management facilities instead.

See `SECURITY.md` for the repository security policy.

---

# Engineering Principles

## Deterministic Business Logic

LLMs are used for understanding and orchestration.

They are not used as the source of truth for transactional clinic rules.

---

## Canonical Data

External systems are normalized into Tia's canonical domain model.

This prevents every workflow from having to understand every external database structure.

---

## Conservative Identity Resolution

Patient records are never merged solely because their names look similar.

Identity operations require stronger identifiers.

---

## Explicit Financial Semantics

Payments, refunds, allocations, and package consumption are represented explicitly instead of being inferred from conversational text.

---

## Safe Historical Migration

Imported historical facts retain provenance and cannot silently overwrite protected runtime activity.

---

## Human Control

AI-assisted administrative actions are designed to remain reviewable and auditable where appropriate.

---

## No Runtime Keyword Routing

Natural-language behavior should not depend on brittle keyword or regex routing.

Semantic understanding belongs in the AI orchestration layer; business correctness belongs in deterministic tools.

---

# Product Direction

Tia's goal is to become an intelligent operating layer for aesthetic clinics.

Instead of requiring clinic staff to manually coordinate multiple disconnected tools, the platform aims to provide a system where:

```text
Patients communicate naturally
          ↓
Tia understands the request
          ↓
Clinic rules determine what is possible
          ↓
Tia executes the authorized operation
          ↓
Canonical clinic data stays synchronized
          ↓
Automations handle follow-up work
          ↓
Analytics show the clinic what is happening
```

The result is not simply an AI chatbot.

It is an **AI-native clinic operations platform** built around real operational workflows, structured data, deterministic business rules, integrations, and automation.

---

# Current Version

See:

```text
VERSION
```

for the current repository version.

---

# License

This project is proprietary software.

Unless explicitly stated otherwise, the source code and associated materials are not licensed for redistribution, modification, or commercial use by third parties.

© Tia AI. All rights reserved.
