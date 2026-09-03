from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def test_persistent_agent_knowledge_page_is_wired() -> None:
    root = _root()
    route = (root / "backend/app/api/routes/clinic.py").read_text(encoding="utf-8")
    page = (root / "frontend/src/app/(dashboard)/knowledge/page.tsx").read_text(encoding="utf-8")
    setup = (root / "frontend/src/app/(dashboard)/setup/page.tsx").read_text(encoding="utf-8")
    assert '@router.get("/knowledge"' in route
    assert 'title="بيانات Tia"' in page
    assert 'href="/knowledge"' in setup
    assert "نفس المصدر الذي تعتمد عليه Tia أثناء العمل" in page


def test_weekly_schedule_editing_remains_available_in_rebuilt_setup() -> None:
    root = _root()
    schedule = (root / "frontend/src/components/weekly-schedule-table.tsx").read_text(encoding="utf-8")
    importer = (root / "frontend/src/app/(dashboard)/setup/setup-importer.tsx").read_text(encoding="utf-8")

    assert 'label: "السبت"' in schedule
    assert 'label: "الجمعة"' in schedule
    assert 'clinic_hours: "مواعيد العيادة"' in importer
    assert 'doctor_hours: "مواعيد الدكاترة الثابتين"' in importer
def test_agent_knowledge_chat_requires_confirmation() -> None:
    root = _root()
    route = (root / "backend/app/api/routes/clinic.py").read_text(encoding="utf-8")
    assistant = (root / "frontend/src/app/(dashboard)/knowledge/assistant.tsx").read_text(encoding="utf-8")
    assert '"/knowledge/ai/propose"' in route
    assert '"/knowledge/ai/apply"' in route
    assert "تأكيد وتنفيذ التعديل" in assistant
    assert "proposal.requires_confirmation" in assistant


def test_clinic_setup_links_to_persistent_agent_knowledge() -> None:
    root = _root()
    setup = (root / "frontend/src/app/(dashboard)/setup/page.tsx").read_text(encoding="utf-8")
    assert 'href="/knowledge"' in setup
    assert "معلومات Tia" in setup


def test_knowledge_server_action_module_exports_async_functions_only() -> None:
    root = _root()
    actions = (root / "frontend/src/app/(dashboard)/knowledge/actions.ts").read_text(encoding="utf-8")
    assistant = (root / "frontend/src/app/(dashboard)/knowledge/assistant.tsx").read_text(encoding="utf-8")
    assert actions.lstrip().startswith('"use server";')
    assert "export async function knowledgeAssistantAction" in actions
    assert "initialKnowledgeAssistantState" not in actions
    assert "const initialKnowledgeAssistantState" in assistant
