from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout_seconds,
    pool_recycle=settings.db_pool_recycle_seconds,
)

# Reporting reads have a separate, intentionally small pool. Saturating this
# pool applies backpressure to Analytics only; the main booking/operations pool
# above remains available for customer-facing work.
analytics_engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.analytics_db_pool_size,
    max_overflow=settings.analytics_db_max_overflow,
    pool_timeout=settings.analytics_db_pool_timeout_seconds,
    pool_recycle=settings.db_pool_recycle_seconds,
    pool_use_lifo=True,
)


class AnalyticsSession(Session):
    """Marker Session class used only by bounded analytics reads."""


@event.listens_for(AnalyticsSession, "after_begin")
def _configure_analytics_transaction(_session, _transaction, connection) -> None:
    # SET LOCAL is applied for every transaction, which also works correctly
    # behind transaction-pooling proxies. It cannot leak into the main engine or
    # a later non-analytics transaction on the same PostgreSQL server session.
    timeout_ms = int(settings.analytics_statement_timeout_ms)
    connection.exec_driver_sql(f"SET LOCAL statement_timeout = {timeout_ms}")
    connection.exec_driver_sql("SET LOCAL application_name = 'tia-analytics'")


SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    expire_on_commit=False,
)

AnalyticsSessionLocal = sessionmaker(
    bind=analytics_engine,
    class_=AnalyticsSession,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
