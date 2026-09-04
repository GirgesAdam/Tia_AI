import json
from pathlib import Path


def test_railway_backend_uses_docker_and_database_readiness_healthcheck() -> None:
    backend = Path(__file__).resolve().parents[1]
    config = json.loads((backend / "railway.json").read_text(encoding="utf-8"))
    dockerfile = (backend / "Dockerfile").read_text(encoding="utf-8")

    assert config["build"]["builder"] == "DOCKERFILE"
    assert config["build"]["dockerfilePath"] == "Dockerfile"
    assert config["deploy"]["healthcheckPath"] == "/api/v1/health/ready"
    assert "${PORT:-8000}" in dockerfile
