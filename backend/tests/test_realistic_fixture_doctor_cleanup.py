from pathlib import Path


def test_realistic_fixture_owns_the_staging_doctor_set() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/seed_realistic_aesthetic_clinic.py").read_text(
        encoding="utf-8"
    )

    assert "fixture_doctor_ids" in source
    assert "outside_fixture = doctor.id not in fixture_doctor_ids" in source
    assert "doctor.booking_enabled = False" in source
    assert "assignment.is_active = False" in source


def test_realistic_seed_preserves_fixture_doctor_identity_when_duplicate_email_exists() -> None:
    """Regression for the v0.47.1 seed failure seen on an already-used demo workspace.

    Historical seed runs could bind the deterministic fixture Doctor id to an
    older Staff row selected by name while another Staff row already owned the
    synthetic fixture email. Re-seeding must keep the Doctor identity/history
    and must not try to merge Staff rows by overwriting the unique email.
    """
    from uuid import uuid4

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models.doctor import Doctor
    from app.models.staff import Staff
    from app.models.user import User
    from app.models.workspace import Workspace
    from app.models.workspace_member import WorkspaceMember  # noqa: F401 - mapper registration
    from scripts.seed_realistic_aesthetic_clinic import DOCTORS, fixture_id, upsert_doctor

    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in (Workspace.__table__, User.__table__, Staff.__table__, Doctor.__table__):
        table.create(engine)

    spec = DOCTORS[0]
    workspace = Workspace(id=uuid4(), name="Fixture test", slug=f"fixture-{uuid4()}")
    legacy_staff = Staff(
        id=uuid4(),
        workspace_id=workspace.id,
        first_name="د. أحمد",
        last_name="محمود",
        email="ahmed@tia.example",
        phone="+200000000001",
        job_title="legacy demo doctor",
        is_active=True,
    )
    email_owner = Staff(
        id=uuid4(),
        workspace_id=workspace.id,
        first_name="Ahmed",
        last_name="Mahmoud",
        email=spec["email"],
        phone="+200000000002",
        job_title="old duplicate",
        is_active=True,
    )
    fixture_doctor = Doctor(
        id=fixture_id(workspace.id, f"doctor:{spec['key']}"),
        workspace_id=workspace.id,
        staff_id=legacy_staff.id,
        specialization="legacy",
        booking_enabled=True,
        is_active=True,
    )

    with Session(engine) as db:
        db.add_all([workspace, legacy_staff, email_owner, fixture_doctor])
        db.commit()

        resolved_staff, resolved_doctor = upsert_doctor(db, workspace, spec)
        db.commit()

        assert resolved_staff.id == legacy_staff.id
        assert resolved_doctor.id == fixture_doctor.id
        assert resolved_staff.first_name == "أحمد"
        assert resolved_staff.last_name == "محمود"
        # The unique fixture email remains on its existing owner; no implicit
        # Staff merge is performed and the historical Doctor id is preserved.
        assert resolved_staff.email == "ahmed@tia.example"
        assert db.get(Staff, email_owner.id).email == spec["email"]
