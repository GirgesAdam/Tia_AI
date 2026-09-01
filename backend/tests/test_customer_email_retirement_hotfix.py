from pathlib import Path
import re

from app.integrations.clinic.authority import PATIENT_EXTERNAL_SYNC_FIELDS
from app.integrations.clinic.base import PatientRecord
from app.integrations.clinic.sync_contract import ExternalPatientSyncRecord
from app.models.channel_identity import ChannelIdentity
from app.models.patient import Patient
from app.schemas.channel import NormalizedInboundMessage
from app.schemas.crm import PatientCreate, PatientRead, PatientUpdate


def test_patient_customer_contract_has_no_email_field() -> None:
    assert "email" not in Patient.__table__.columns
    assert "email" not in ChannelIdentity.__table__.columns
    assert "email" not in NormalizedInboundMessage.model_fields
    for schema in (PatientCreate, PatientUpdate, PatientRead):
        assert "email" not in schema.model_fields
    assert "email" not in ExternalPatientSyncRecord.__dataclass_fields__
    assert "email_verified" not in ExternalPatientSyncRecord.__dataclass_fields__
    assert "email" not in PatientRecord.__dataclass_fields__
    assert "email" not in PATIENT_EXTERNAL_SYNC_FIELDS


def test_customer_email_agent_capability_is_retired() -> None:
    backend = Path(__file__).resolve().parent.parent
    tools = (backend / "app/agents/tools/clinic_tools.py").read_text(encoding="utf-8")
    router = (backend / "app/agents/semantic_router.py").read_text(encoding="utf-8")
    policy = (backend / "app/agents/capability_policy.py").read_text(encoding="utf-8")
    assert "send_email_to_customer" not in tools
    assert "email_communication" not in router
    assert "email_communication" not in policy


def test_frontend_patient_views_do_not_reference_patient_email() -> None:
    root = Path(__file__).resolve().parents[2] / "frontend" / "src"
    targets = [
        root / "lib/types.ts",
        root / "lib/agent-knowledge-types.ts",
        root / "app/(dashboard)/patients/page.tsx",
        root / "app/(dashboard)/patients/[patientId]/page.tsx",
        root / "app/(dashboard)/inbox/page.tsx",
        root / "app/(dashboard)/inbox/[conversationId]/page.tsx",
        root / "app/(dashboard)/knowledge/page.tsx",
    ]
    joined = "\n".join(path.read_text(encoding="utf-8") for path in targets)
    assert "patient.email" not in joined
    assert "KnowledgePatient = { id: string; name: string; phone: string | null; email:" not in joined


def test_alembic_revision_ids_fit_default_version_column_and_new_chain_is_short() -> None:
    backend = Path(__file__).resolve().parent.parent
    revisions: dict[str, str | None] = {}
    for path in (backend / "alembic/versions").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        revision_match = re.search(r'^revision:\s*str\s*=\s*["\']([^"\']+)', source, re.M)
        if revision_match is None:
            continue
        revision = revision_match.group(1)
        assert len(revision) <= 32, f"Alembic revision exceeds VARCHAR(32): {revision}"
        down_match = re.search(r'^down_revision:.*?=\s*["\']([^"\']+)', source, re.M)
        revisions[revision] = down_match.group(1) if down_match else None

    assert revisions["0033_sync_authority"] == "0032_external_sync_engine"
    assert revisions["0034_drop_customer_email"] == "0033_sync_authority"


def test_drop_patient_email_migration_is_explicit() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "alembic/versions/0034_drop_customer_email.py").read_text(encoding="utf-8")
    assert 'op.drop_column("patients", "email")' in source
    assert 'revision: str = "0034_drop_customer_email"' in source
    assert 'down_revision: str | Sequence[str] | None = "0033_sync_authority"' in source
