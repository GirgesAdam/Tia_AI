from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

PATIENT_NOTE_TYPES = ("general", "preference", "customer_service", "follow_up")


class PatientNote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "patient_notes"
    __table_args__ = (
        CheckConstraint(
            "note_type IN ('general', 'preference', 'customer_service', 'follow_up')",
            name="patient_note_type_valid",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "patient_id"],
            ["patients.workspace_id", "patients.id"],
            ondelete="CASCADE",
            name="fk_patient_notes_patient",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    author_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    note_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="general",
        server_default="general",
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
