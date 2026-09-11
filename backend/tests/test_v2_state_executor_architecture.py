from pathlib import Path


FILES = (
    Path("app/services/agent_v2/state_executor.py"),
    Path("app/services/agent_v2/active_task_progress.py"),
)


def test_state_workflow_layer_stays_pure_python() -> None:
    forbidden = (
        "sqlalchemy",
        "Session",
        "get_clinic_adapter",
        "ClinicAdapter",
        "langchain",
        "openai",
        "invoke_model",
        "invoke_with_model_chain",
        "agent_chat",
        "tia_customer_agent",
        "grounded_response_composer",
        "db.commit",
        "db.flush",
        "db.add",
        "re.compile",
        "difflib",
    )
    for path in FILES:
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{path} must not contain {token!r}"
