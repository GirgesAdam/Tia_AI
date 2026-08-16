from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.appointment import Appointment
from app.models.branch import Branch
from app.models.patient import Patient
from app.models.service import Service
from app.models.workspace import Workspace
from final_gate_scenarios import GATE_MARKER, gate_ids
from staging_scenarios import sid


class FixtureQualityError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureQualityError(message)


def _safe_phone(phone: str | None) -> bool:
    # Final/staging contacts use syntactically valid but deliberately
    # non-routable-looking +20 00... numbers. Never use a real-looking +20 1x
    # Egyptian mobile in automated test fixtures.
    return phone is None or phone.startswith("+200000")


def validate(workspace_id: UUID) -> list[str]:
    if settings.is_production:
        raise FixtureQualityError("Fixture validation refuses production.")

    ids = gate_ids(workspace_id)
    notes: list[str] = []

    with SessionLocal() as db:
        primary = db.get(Workspace, workspace_id)
        secondary = db.get(Workspace, ids["secondary_workspace"])
        _require(primary is not None, "Primary workspace is missing.")
        _require(secondary is not None, "Secondary Final Gate workspace is missing.")

        gate_patient_ids = (
            ids["race_patient_a"],
            ids["race_patient_b"],
            ids["member_patient"],
            ids["automation_reschedule_patient"],
            ids["automation_cancel_patient"],
            ids["channel_patient"],
            ids["secondary_patient"],
        )
        patients = list(
            db.scalars(
                select(Patient).where(Patient.id.in_(gate_patient_ids))
            )
        )
        _require(
            len(patients) == len(gate_patient_ids),
            "One or more Final Gate patients are missing.",
        )

        full_names = {f"{p.first_name} {p.last_name or ''}".strip() for p in patients}
        expected_names = {
            "محمود سامح",
            "سلمى عادل",
            "ياسمين خالد",
            "نورهان شريف",
            "كريم وائل",
            "هند مصطفى",
            "ريم حسام",
        }
        _require(
            expected_names.issubset(full_names),
            "Final Gate patient names are not the approved realistic synthetic set.",
        )

        for patient in patients:
            _require(
                _safe_phone(patient.phone),
                f"Unsafe real-looking test phone on patient {patient.id}.",
            )
            _require(
                patient.preferred_language == "ar",
                f"Unexpected language on patient {patient.id}.",
            )
            _require(
                patient.source_detail == GATE_MARKER,
                f"Patient {patient.id} is missing the test-data marker.",
            )
            _require(
                patient.marketing_consent is False,
                f"Test patient {patient.id} must never have marketing consent.",
            )
            if patient.email:
                _require(
                    patient.email.endswith(".example"),
                    f"Test patient email is not on a reserved .example domain: {patient.email}",
                )

        secondary_branch = db.get(Branch, ids["secondary_branch"])
        secondary_service = db.get(Service, ids["secondary_service"])
        secondary_appt = db.get(Appointment, ids["secondary_appointment"])

        _require(secondary_branch is not None, "Secondary branch is missing.")
        _require(secondary_branch.city == "Cairo", "Secondary branch city must be Cairo.")
        _require(
            secondary_branch.timezone == "Africa/Cairo",
            "Secondary branch timezone must be Africa/Cairo.",
        )

        _require(secondary_service is not None, "Secondary service is missing.")
        _require(
            15 <= secondary_service.duration_minutes <= 240,
            "Secondary service duration is not operationally plausible.",
        )
        _require(
            10000 <= secondary_service.price_minor <= 10000000,
            "Secondary service EGP price is not operationally plausible.",
        )
        _require(
            secondary_service.currency == "EGP",
            "Secondary service currency must be EGP.",
        )

        _require(secondary_appt is not None, "Secondary appointment is missing.")
        _require(
            secondary_appt.end_at > secondary_appt.start_at,
            "Secondary appointment has an invalid time range.",
        )
        _require(
            secondary_appt.duration_minutes == secondary_service.duration_minutes,
            "Secondary appointment duration does not match the service.",
        )

        regression_branch = db.get(Branch, sid(workspace_id, "branch:regression-main"))
        _require(regression_branch is not None, "Full staging regression clinic is missing.")
        _require(
            _safe_phone(regression_branch.phone),
            "Full staging branch still has a real-looking mobile number.",
        )
        if regression_branch.email:
            _require(
                regression_branch.email.endswith(".example"),
                "Full staging branch email is not on a reserved .example domain.",
            )

        regression_patients = list(
            db.scalars(
                select(Patient).where(
                    Patient.workspace_id == workspace_id,
                    Patient.source_detail == "tia-full-staging-regression",
                )
            )
        )
        for patient in regression_patients:
            _require(
                _safe_phone(patient.phone),
                f"Full staging patient {patient.id} has a real-looking mobile number.",
            )
            if patient.email:
                _require(
                    patient.email.endswith(".example"),
                    f"Full staging patient {patient.id} email is not .example.",
                )

        notes.append(f"Validated Final Gate patients: {len(patients)}")
        notes.append(f"Validated full-staging marked patients: {len(regression_patients)}")
        notes.append("Synthetic contacts are non-routable-looking and marked as test data.")
        notes.append("Clinic timezone/currency/service duration/price/appointment ranges are plausible.")

    return notes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", required=True)
    args = parser.parse_args()

    try:
        notes = validate(UUID(args.workspace_id))
    except (ValueError, FixtureQualityError) as exc:
        print(f"[FAIL] Fixture data quality — {exc}")
        return 2

    for note in notes:
        print(f"[PASS] {note}")
    print("[PASS] Fixture data quality")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
