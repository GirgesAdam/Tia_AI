"""normalize stored doctor names

Revision ID: 0040_doctor_name_hygiene
Revises: 0039_crm_campaigns
Create Date: 2026-08-29
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0040_doctor_name_hygiene"
down_revision: str | None = "0039_crm_campaigns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TITLE_RE = re.compile(
    r"^(?:(?:(?:أ|ا)\s*\.\s*د\s*\.?|د\.|dr\.|prof\.)\s*|(?:د|دكتور|دكتورة|dr|doctor|prof|professor)\s+)+",
    flags=re.IGNORECASE,
)


def _clean(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _normalized_parts(first_name: str, last_name: str) -> tuple[str, str]:
    text = _clean(f"{first_name or ''} {last_name or ''}")
    previous = None
    while text and text != previous:
        previous = text
        text = _TITLE_RE.sub("", text).strip()
    parts = _clean(text).split(" ") if _clean(text) else []
    if not parts:
        return _clean(first_name), _clean(last_name)
    if len(parts) == 1:
        return parts[0], ""
    return " ".join(parts[:-1]), parts[-1]


def _deactivate_known_synthetic_catalog_records(bind) -> None:
    """Remove old demo/regression clinic-core rows from active catalogs.

    Older staging seeds used the primary ``tia`` workspace. Those rows are
    intentionally retained for referential/history safety, but they must not
    remain active after regression data moved to its own workspace. The email
    suffixes below are Tia-owned synthetic domains, not clinic data.
    """
    bind.execute(
        sa.text(
            """
            UPDATE doctors AS d
            SET is_active = FALSE, booking_enabled = FALSE
            WHERE EXISTS (
                SELECT 1
                FROM staff AS s
                JOIN workspaces AS w ON w.id = s.workspace_id
                WHERE s.id = d.staff_id
                  AND s.workspace_id = d.workspace_id
                  AND w.slug = 'tia'
                  AND (
                      LOWER(COALESCE(s.email, '')) LIKE '%@tia.example'
                      OR LOWER(COALESCE(s.email, '')) LIKE '%@tia.local'
                  )
            )
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE branches
            SET is_active = FALSE
            WHERE workspace_id IN (SELECT id FROM workspaces WHERE slug = 'tia')
              AND (LOWER(COALESCE(code, '')) LIKE 'regression-%'
                   OR LOWER(COALESCE(code, '')) LIKE 'demo-%')
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE services
            SET is_active = FALSE
            WHERE workspace_id IN (SELECT id FROM workspaces WHERE slug = 'tia')
              AND (LOWER(COALESCE(slug, '')) LIKE 'regression-%'
                   OR LOWER(COALESCE(slug, '')) LIKE 'demo-%')
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE staff AS s
            SET is_active = FALSE
            WHERE s.workspace_id IN (SELECT id FROM workspaces WHERE slug = 'tia')
              AND (
                LOWER(COALESCE(s.email, '')) LIKE '%@tia.example'
                OR LOWER(COALESCE(s.email, '')) LIKE '%@tia.local'
            )
              AND EXISTS (
                  SELECT 1
                  FROM doctors AS d
                  WHERE d.staff_id = s.id
                    AND d.workspace_id = s.workspace_id
              )
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT DISTINCT s.id, s.first_name, s.last_name
            FROM staff AS s
            JOIN doctors AS d
              ON d.workspace_id = s.workspace_id
             AND d.staff_id = s.id
            """
        )
    ).mappings()
    for row in rows:
        first_name, last_name = _normalized_parts(row["first_name"], row["last_name"])
        if first_name == row["first_name"] and last_name == row["last_name"]:
            continue
        bind.execute(
            sa.text(
                "UPDATE staff SET first_name = :first_name, last_name = :last_name WHERE id = :staff_id"
            ),
            {"staff_id": row["id"], "first_name": first_name, "last_name": last_name},
        )

    _deactivate_known_synthetic_catalog_records(bind)


def downgrade() -> None:
    # Presentation prefixes are intentionally not reconstructed. They were not
    # identity data and their original spelling cannot be recovered reliably.
    pass
