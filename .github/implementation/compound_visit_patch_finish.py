from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, value: str) -> None:
    (ROOT / path).write_text(value, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    value = read(path)
    if value.count(old) != 1:
        raise RuntimeError(f"expected one finish match in {path}; got {value.count(old)}")
    write(path, value.replace(old, new, 1))


preflight = "backend/app/services/agent_v2/compound_visit_preflight.py"
old = '''    This prevents partial visits such as booking service A and only then discovering
    that service B cannot follow it.
    """
    groups: dict[str, list[PlanStep]] = {}
'''
new = '''    This prevents partial visits such as booking service A and only then discovering
    that service B cannot follow it.
    """
    plan = _auto_resolve_grouped_visits(
        plan,
        context=context,
        timezone_name=timezone_name,
        visit_group_id=visit_group_id,
    )
    groups: dict[str, list[PlanStep]] = {}
'''
replace_once(preflight, old, new)

# The first-stage patch intentionally stops at the insertion above when the old
# source shape is ambiguous. Reuse the already-reviewed tail for orchestrator
# plumbing and focused tests rather than duplicating it here.
source = (ROOT / ".github/implementation/compound_visit_patch.py").read_text(encoding="utf-8")
marker = "# ---- orchestrator: stable group id + nested transaction rollback barrier -----"
position = source.index(marker)
tail = source[position:]
namespace = {
    "__file__": str(ROOT / ".github/implementation/compound_visit_patch.py"),
    "__name__": "__compound_finish__",
    "ROOT": ROOT,
    "text": read,
    "write": write,
    "replace_once": replace_once,
}
exec(compile(tail, "compound_visit_patch_tail.py", "exec"), namespace, namespace)
print("compound visit patch finish applied")
