"""Repair scheduling/billing schema drift after revision 0077.

Revision ID: 0078_repair_schedule_billing_categories
Revises: 0077_schedule_billing_categories

Revision 0077 existed in production in an earlier shape before its repository
definition changed.  This repair migration reconciles an already-stamped 0077
database with the canonical schema represented by the current models.  On a
clean database upgraded through the current 0077 definition, the structural
operations below are effectively no-ops apart from safe backfill/security
enforcement.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0078_repair_schedule_billing_categories"
down_revision: str | Sequence[str] | None = "0077_schedule_billing_categories"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _column_names(table_name: str) -> set[str]:
    return {str(row["name"]) for row in _inspector().get_columns(table_name)}


def _check_names(table_name: str) -> set[str]:
    return {
        str(row["name"])
        for row in _inspector().get_check_constraints(table_name)
        if row.get("name")
    }


def _check_name(table_name: str, logical_name: str) -> str | None:
    expected = {
        logical_name,
        f"ck_{table_name}_{logical_name}",
    }
    for name in _check_names(table_name):
        if name in expected or name.endswith(f"_{logical_name}"):
            return name
    return None


def _table_names() -> set[str]:
    return set(_inspector().get_table_names(schema="public"))


def upgrade() -> None:
    if "discount_minor" not in _column_names("appointments"):
        op.add_column(
            "appointments",
            sa.Column(
                "discount_minor",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
    if _check_name("appointments", "appointment_discount_non_negative") is None:
        op.create_check_constraint(
            "appointment_discount_non_negative",
            "appointments",
            "discount_minor >= 0",
        )

    if "operational_category" not in _column_names("services"):
        op.add_column(
            "services",
            sa.Column(
                "operational_category",
                sa.String(length=20),
                nullable=False,
                server_default="dermatology",
            ),
        )
    op.execute(
        sa.text(
            """
            UPDATE services
            SET operational_category = CASE
                WHEN requires_laser_device
                  OR lower(coalesce(category, '')) LIKE '%laser%'
                    THEN 'laser'
                WHEN lower(coalesce(category, '')) LIKE '%slim%'
                  OR lower(coalesce(category, '')) LIKE '%weight%'
                  OR lower(coalesce(category, '')) LIKE '%body contour%'
                    THEN 'slimming'
                ELSE 'dermatology'
            END
            """
        )
    )
    if _check_name("services", "service_operational_category_valid") is None:
        op.create_check_constraint(
            "service_operational_category_valid",
            "services",
            "operational_category IN ('laser', 'dermatology', 'slimming')",
        )

    # An earlier 0077 shape repurposed services.category as the operational
    # taxonomy.  The current model keeps category as optional legacy/display
    # metadata and stores scheduling taxonomy separately.
    legacy_category_check = _check_name("services", "service_category_valid")
    if legacy_category_check is not None:
        op.drop_constraint(op.f(legacy_category_check), "services", type_="check")
    op.alter_column(
        "services",
        "category",
        existing_type=sa.String(length=120),
        nullable=True,
        server_default=None,
    )

    if "doctor_service_categories" not in _table_names():
        op.create_table(
            "doctor_service_categories",
            sa.Column("workspace_id", sa.Uuid(), nullable=False),
            sa.Column("doctor_id", sa.Uuid(), nullable=False),
            sa.Column("category", sa.String(length=20), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.CheckConstraint(
                "category IN ('laser', 'dermatology', 'slimming')",
                name="doctor_service_category_valid",
            ),
            sa.ForeignKeyConstraint(
                ["workspace_id", "doctor_id"],
                ["doctors.workspace_id", "doctors.id"],
                ondelete="CASCADE",
                name="fk_doctor_service_categories_doctor",
            ),
            sa.PrimaryKeyConstraint(
                "workspace_id",
                "doctor_id",
                "category",
                name="pk_doctor_service_categories",
            ),
        )

    op.execute(
        sa.text(
            """
            INSERT INTO doctor_service_categories
                (workspace_id, doctor_id, category)
            SELECT DISTINCT
                assignment.workspace_id,
                assignment.doctor_id,
                service.operational_category
            FROM doctor_services AS assignment
            JOIN services AS service
              ON service.workspace_id = assignment.workspace_id
             AND service.id = assignment.service_id
            WHERE assignment.is_active
              AND service.is_active
            ON CONFLICT DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            'ALTER TABLE public."doctor_service_categories" ENABLE ROW LEVEL SECURITY'
        )
    )
    op.execute(
        sa.text(
            'REVOKE ALL ON TABLE public."doctor_service_categories" FROM anon, authenticated'
        )
    )

    # Remove the denormalized array left by the earlier production 0077 shape.
    if "service_categories" in _column_names("doctors"):
        op.drop_column("doctors", "service_categories")


def downgrade() -> None:
    # This is a drift-repair revision.  The canonical 0077 schema already
    # contains the structures retained after this repair, so reverting the
    # revision marker must not recreate the historical drift.
    pass
