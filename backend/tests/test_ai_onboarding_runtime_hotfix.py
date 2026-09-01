import re
from pathlib import Path

import pytest
from sqlalchemy import JSON, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def test_sqlalchemy_metadata_attribute_is_reserved() -> None:
    class Base(DeclarativeBase):
        pass

    with pytest.raises(Exception) as exc_info:

        class BadEvent(Base):
            __tablename__ = "bad_event_for_contract_test"
            id: Mapped[int] = mapped_column(Integer, primary_key=True)
            metadata: Mapped[dict] = mapped_column(JSON)

    assert "metadata" in str(exc_info.value).lower()
    assert "reserved" in str(exc_info.value).lower()


def test_onboarding_event_maps_database_metadata_column_with_safe_attribute() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/models/onboarding_ai_event.py").read_text(encoding="utf-8")

    assert re.search(r"^\s+metadata:\s*Mapped", source, re.MULTILINE) is None
    assert re.search(r"^\s+event_metadata:\s*Mapped", source, re.MULTILINE)
    assert 'mapped_column(\n        "metadata",' in source


def test_onboarding_service_uses_safe_event_metadata_attribute() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/services/ai_onboarding.py").read_text(encoding="utf-8")

    assert "event_metadata=metadata or {}" in source
    assert re.search(r"(?<!event_)metadata=metadata or \{\}", source) is None


def test_onboarding_route_surfaces_missing_migration_as_503() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "app/api/routes/onboarding.py").read_text(encoding="utf-8")

    assert "except ProgrammingError as exc" in source
    assert "0013_ai_onboarding_sessions" in source
    assert "Run Alembic upgrade head" in source
