from pathlib import Path


def test_railway_backend_docker_runtime_exposes_expected_port_contract() -> None:
    backend = Path(__file__).resolve().parents[1]
    dockerfile = (backend / "Dockerfile").read_text(encoding="utf-8")
    health = (backend / "app/api/routes/health.py").read_text(encoding="utf-8")

    assert "EXPOSE 8000" in dockerfile
    assert "uvicorn app.main:app" in dockerfile
    assert "${PORT:-8000}" in dockerfile
    assert '@router.get("/ready")' in health
    assert 'db.execute(text("SELECT 1"))' in health
