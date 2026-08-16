from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PatientTag(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "patient_tags"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_patient_tags_workspace_id_id"),
        UniqueConstraint(
            "workspace_id",
            "normalized_name",
            name="uq_patient_tags_workspace_normalized_name",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )


class PatientTagAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "patient_tag_assignments"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "patient_id",
            "tag_id",
            name="uq_patient_tag_assignments_patient_tag",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_patient_tag_assignments_patient",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "tag_id"],
            ["patient_tags.workspace_id", "patient_tags.id"],
            ondelete="CASCADE",
            name="fk_patient_tag_assignments_tag",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    tag_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
