from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()

# Production-grade pool + a server-side statement timeout so a runaway query
# can't pin a connection forever. Dev/test keep it light.
_engine_kw: dict = {"pool_pre_ping": True, "future": True}
if _settings.app_env in ("production", "staging"):
    _engine_kw.update(
        pool_size=10, max_overflow=10, pool_timeout=30, pool_recycle=1800,
        connect_args={"options": "-c statement_timeout=60000 -c idle_in_transaction_session_timeout=120000"},
    )
engine = create_engine(_settings.database_url, **_engine_kw)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@contextmanager
def session_scope() -> Iterator:
    """Transactional session context. Commits on success, rolls back on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
