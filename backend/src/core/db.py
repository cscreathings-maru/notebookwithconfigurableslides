"""Database engine and session management.

Synchronous SQLAlchemy 2.0 (psycopg3). FastAPI runs sync dependencies in a
threadpool, which keeps the data layer simple and transactional. Portable column
types (Uuid, JSON, LargeBinary) let the same models run on SQLite under tests.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

_settings = get_settings()

# pool_pre_ping guards against stale connections after engine/db restarts.
engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session; commits on success, rolls back on error."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
