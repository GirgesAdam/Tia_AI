from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

PACKAGE_SESSION_COUNTS = (3, 6, 9)


class ServicePackageOffer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Admin-configured sellable laser package for one service and device.

    PatientPackage snapshots the commercial facts at purchase time, so changing or
    disabling this offer never mutates packages that patients already own.
    """

    __tablename__ = "service_package_offers"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_service_package_offers_workspace_id_id"),
        UniqueConstraint(
            "workspace_id",
            "service_id",
            "device_key",
            "sessions_count",
            name="uq_service_package_offers_workspace_service_device_sessions",
        ),
        CheckConstraint(
            "device_key IN ('prime_lase', 'candela_gentle')",
            name="service_package_offer_device_valid",
        ),
        CheckConstraint(
            "sessions_count IN (3, 6, 9)",
            name="service_package_offer_sessions_valid",
        ),
        CheckConstraint("price_minor >= 0", name="service_package_offer_price_non_negative"),
        ForeignKeyConstraint(
            ["workspace_id", "service_id"],
            ["services.workspace_id", "services.id"],
            ondelete="CASCADE",
            name="fk_service_package_offers_service",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    service_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    device_key: Mapped[str] = mapped_column(String(40), nullable=False)
    device_name: Mapped[str] = mapped_column(String(120), nullable=False)
    sessions_count: Mapped[int] = mapped_column(Integer, nullable=False)
    price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EGP", server_default="EGP")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
