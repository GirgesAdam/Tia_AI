from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.patient_package import PackageUsage, PatientPackage
from app.services.patient_packages import validate_package_for_booking


def test_unpaid_package_can_still_reserve_sessions() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    PatientPackage.__table__.create(engine)
    PackageUsage.__table__.create(engine)

    workspace_id = uuid4()
    patient_id = uuid4()
    service_id = uuid4()
    purchased_at = datetime.now(UTC) - timedelta(days=7)

    with Session(engine) as db:
        package = PatientPackage(
            workspace_id=workspace_id,
            patient_id=patient_id,
            service_id=service_id,
            purchase_transaction_id=None,
            created_by_user_id=None,
            external_id=None,
            name="6 sessions",
            sessions_purchased=6,
            opening_sessions_remaining=None,
            sessions_total_known=True,
            sale_price_minor=600_000,
            standalone_session_price_minor_at_purchase=120_000,
            currency="EGP",
            purchased_at=purchased_at,
            expires_at=date.today() + timedelta(days=365),
            status="active",
            source="staff",
            idempotency_key=None,
        )
        db.add(package)
        db.flush()

        selected = validate_package_for_booking(
            db,
            workspace_id=workspace_id,
            package_id=package.id,
            patient_id=patient_id,
            service_id=service_id,
            appointment_start_at=datetime.now(UTC) + timedelta(days=2),
            sessions=1,
        )

        assert selected.id == package.id
        assert selected.purchase_transaction_id is None
        assert selected.sale_price_minor == 600_000
