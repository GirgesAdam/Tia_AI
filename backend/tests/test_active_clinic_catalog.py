from types import SimpleNamespace
from uuid import UUID

from app.agents.clinic_grounding import _filter_bookable_doctor_rows


def _doctor(value: str):
    return SimpleNamespace(id=UUID(value))


def test_catalog_excludes_doctor_without_complete_bookable_graph() -> None:
    doctor_a = _doctor("00000000-0000-0000-0000-000000000001")
    doctor_b = _doctor("00000000-0000-0000-0000-000000000002")
    doctor_c = _doctor("00000000-0000-0000-0000-000000000003")
    doctor_d = _doctor("00000000-0000-0000-0000-000000000004")
    staff = SimpleNamespace(first_name="Test", last_name="Doctor")

    rows = _filter_bookable_doctor_rows(
        [
            (doctor_a, staff),
            (doctor_b, staff),
            (doctor_c, staff),
            (doctor_d, staff),
        ],
        service_ids_by_doctor={
            doctor_a.id: ["service-a"],
            doctor_b.id: ["service-b"],
            doctor_d.id: ["service-d"],
        },
        branch_ids_by_doctor={
            doctor_a.id: ["branch-a"],
            doctor_c.id: ["branch-c"],
            doctor_d.id: ["branch-d"],
        },
        scheduled_branch_ids_by_doctor={
            doctor_a.id: ["branch-a"],
            # doctor_d deliberately has no configured working-hours schedule.
        },
    )

    assert [doctor.id for doctor, _ in rows] == [doctor_a.id]


def test_catalog_requires_schedule_on_an_assigned_active_branch() -> None:
    doctor = _doctor("00000000-0000-0000-0000-000000000005")
    staff = SimpleNamespace(first_name="Test", last_name="Doctor")

    rows = _filter_bookable_doctor_rows(
        [(doctor, staff)],
        service_ids_by_doctor={doctor.id: ["service-a"]},
        branch_ids_by_doctor={doctor.id: ["branch-a"]},
        scheduled_branch_ids_by_doctor={doctor.id: ["branch-b"]},
    )

    assert rows == []
