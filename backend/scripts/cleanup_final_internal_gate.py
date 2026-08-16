from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, func, select

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.appointment import Appointment
from app.models.automation_job import AutomationJob
from app.models.automation_rule import AutomationRule
from app.models.conversation import Conversation
from app.models.handoff_request import HandoffRequest
from app.models.patient import Patient
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from final_gate_scenarios import gate_ids


def cleanup_database(workspace_id: UUID, member_email: str) -> None:
    ids = gate_ids(workspace_id)
    primary_patients = [
        ids["race_patient_a"], ids["race_patient_b"], ids["member_patient"],
        ids["automation_reschedule_patient"], ids["automation_cancel_patient"],
        ids["channel_patient"],
    ]
    with SessionLocal() as db:
        db.execute(delete(AutomationJob).where(
            AutomationJob.workspace_id == workspace_id,
            AutomationJob.patient_id.in_(primary_patients),
        ))
        db.execute(delete(Appointment).where(
            Appointment.workspace_id == workspace_id,
            Appointment.patient_id.in_(primary_patients),
        ))
        db.execute(delete(HandoffRequest).where(
            HandoffRequest.workspace_id == workspace_id,
            HandoffRequest.id == ids["channel_handoff"],
        ))
        db.execute(delete(Conversation).where(
            Conversation.workspace_id == workspace_id,
            Conversation.patient_id.in_(primary_patients),
        ))
        db.execute(delete(Patient).where(
            Patient.workspace_id == workspace_id,
            Patient.id.in_(primary_patients),
        ))
        db.execute(delete(AutomationRule).where(
            AutomationRule.workspace_id == workspace_id,
            AutomationRule.id == ids["automation_rule"],
        ))
        secondary = db.get(Workspace, ids["secondary_workspace"])
        if secondary is not None:
            db.delete(secondary)
            db.flush()
        user = db.scalar(select(User).where(User.email == member_email))
        if user is not None:
            db.execute(delete(WorkspaceMember).where(
                WorkspaceMember.user_id == user.id,
                WorkspaceMember.workspace_id == workspace_id,
            ))
            db.flush()
            remaining = db.scalar(
                select(func.count()).select_from(WorkspaceMember).where(
                    WorkspaceMember.user_id == user.id
                )
            )
            if int(remaining or 0) == 0:
                db.delete(user)
        db.commit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--member-email", required=True)
    args = parser.parse_args()
    if settings.is_production:
        print("Refusing final-gate cleanup in production.", file=sys.stderr)
        return 2
    cleanup_database(UUID(args.workspace_id), args.member_email)
    print("Final internal gate database fixtures removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
