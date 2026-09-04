from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


EXPECTED_HEAD = "0056_merge_automation_expenses"


def test_alembic_has_one_current_head() -> None:
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == [EXPECTED_HEAD]
