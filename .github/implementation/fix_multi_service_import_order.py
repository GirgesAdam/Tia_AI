from pathlib import Path

path = Path("backend/app/services/agent_v2/orchestrator.py")
text = path.read_text(encoding="utf-8")
import_line = "from app.services.agent_v2.turn_normalization import expand_multi_service_operations\n"
if text.count(import_line) != 1:
    raise RuntimeError(f"Expected one generated normalization import, found {text.count(import_line)}")
text = text.replace(import_line, "", 1)
marker = "    save_active_task,\n)\n\nV2WriteExecutor ="
if text.count(marker) != 1:
    raise RuntimeError(f"Expected one state-persistence import marker, found {text.count(marker)}")
text = text.replace(
    marker,
    "    save_active_task,\n)\nfrom app.services.agent_v2.turn_normalization import expand_multi_service_operations\n\nV2WriteExecutor =",
    1,
)
path.write_text(text, encoding="utf-8")
