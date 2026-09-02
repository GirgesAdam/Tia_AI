from __future__ import annotations

# One-time safe fix for the booking branch-scope bug.
#
# Problem:
#   _active_branches() currently applies workspace.primary_branch_id as a global
#   filter. In a multi-branch workspace this removes valid active branches before
#   get_booking_options() can match an explicitly requested branch_id.
#
# Correct invariant:
#   _active_branches() returns all active branches in the workspace.
#   Branch preference/defaulting belongs to the caller, not this base query.

from pathlib import Path
import shutil
import sys


OLD = '''def _active_branches(ctx: AgentToolContext) -> list[Branch]:
    stmt = select(Branch).where(
        Branch.workspace_id == ctx.workspace.id,
        Branch.is_active.is_(True),
    )
    if ctx.workspace.primary_branch_id is not None:
        stmt = stmt.where(Branch.id == ctx.workspace.primary_branch_id)
    return list(ctx.db.scalars(stmt.order_by(Branch.name)))
'''

NEW = '''def _active_branches(ctx: AgentToolContext) -> list[Branch]:
    # A workspace primary branch is a default/preference, not a visibility
    # boundary. Booking may explicitly target any active branch in the workspace.
    return list(
        ctx.db.scalars(
            select(Branch)
            .where(
                Branch.workspace_id == ctx.workspace.id,
                Branch.is_active.is_(True),
            )
            .order_by(Branch.name)
        )
    )
'''


def _project_root() -> Path:
    here = Path.cwd().resolve()

    if (here / "app/agents/tools/clinic_tools.py").exists():
        return here.parent

    if (here / "backend/app/agents/tools/clinic_tools.py").exists():
        return here

    raise RuntimeError(
        "Could not find backend/app/agents/tools/clinic_tools.py. "
        "Run this script from the project root or from backend/."
    )


def main() -> int:
    root = _project_root()
    target = root / "backend/app/agents/tools/clinic_tools.py"
    backup = target.with_name("clinic_tools.py.before_branch_scope_fix")

    source = target.read_text(encoding="utf-8")

    if NEW in source:
        print("Branch-scope fix is already applied. No changes made.")
        return 0

    if OLD not in source:
        print(
            "Refusing to edit: the expected _active_branches() block was not found.\n"
            "Your clinic_tools.py differs from the version this fix targets.",
            file=sys.stderr,
        )
        return 2

    if not backup.exists():
        shutil.copy2(target, backup)

    updated = source.replace(OLD, NEW, 1)
    target.write_text(updated, encoding="utf-8")

    print(f"Updated: {target}")
    print(f"Backup:  {backup}")
    print("Change: primary_branch_id is no longer a global active-branch filter.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
