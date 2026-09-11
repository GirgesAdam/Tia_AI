from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_doctor_use_server_module_exports_only_server_actions_at_runtime() -> None:
    actions = (ROOT / "frontend/src/app/(dashboard)/doctors/actions.ts").read_text(
        encoding="utf-8"
    )
    panel = (ROOT / "frontend/src/app/(dashboard)/doctors/doctor-management.tsx").read_text(
        encoding="utf-8"
    )

    assert actions.startswith('"use server";')
    assert "export const initialDoctorAdminState" not in actions
    assert "const initialDoctorAdminState: DoctorAdminState" in panel
    assert "export async function createDoctorAction" in actions
    assert "export async function updateDoctorAction" in actions
    assert "export async function updateDoctorScheduleAction" in actions
    assert "export async function removeDoctorAction" in actions


def test_create_doctor_editor_is_react_controlled_across_revalidation() -> None:
    panel = (ROOT / "frontend/src/app/(dashboard)/doctors/doctor-management.tsx").read_text(
        encoding="utf-8"
    )
    create_form = panel.split("function CreateDoctorForm", 1)[1].split(
        "function DoctorProfileForm", 1
    )[0]

    assert "const [open, setOpen] = useState(false);" in create_form
    assert "aria-expanded={open}" in create_form
    assert "{open && (" in create_form
    assert "<details" not in create_form
