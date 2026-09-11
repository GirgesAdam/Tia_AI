from pathlib import Path


def test_fastapi_lifespan_starts_native_scheduler_when_enabled() -> None:
    root = Path(__file__).resolve().parent.parent
    source = (root / "app/main.py").read_text(encoding="utf-8")
    config = (root / "app/core/config.py").read_text(encoding="utf-8")
    runtime = (root / "app/runtime/automation_scheduler.py").read_text(encoding="utf-8")

    assert "automation_scheduler_enabled" in config
    assert "run_forever" in source
    assert "asyncio.create_task" in source
    assert "await scheduler_task" in source
    assert "async def run_forever" in runtime
