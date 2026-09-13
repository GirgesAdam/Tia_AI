from __future__ import annotations

from sqlalchemy.orm import Session, SessionTransaction


def begin_group_savepoint(db: Session) -> SessionTransaction:
    """Open a savepoint while leaving the caller-owned outer transaction untouched."""
    return db.begin_nested()


def release_group_savepoint(transaction: SessionTransaction) -> None:
    """Release only the grouped-write savepoint, never the outer turn transaction."""
    transaction.commit()


def rollback_group_savepoint(transaction: SessionTransaction) -> None:
    """Rollback only the grouped-write savepoint."""
    transaction.rollback()
