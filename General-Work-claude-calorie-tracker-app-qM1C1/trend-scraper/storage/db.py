"""
Database connection and session management.

The module exposes:
  - ``engine``       – SQLAlchemy Engine (singleton)
  - ``SessionLocal`` – session factory (use as a context manager)
  - ``get_db()``     – FastAPI dependency that yields a session per request
  - ``init_db()``    – create all tables (call at startup)
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.settings import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


# ── Engine ────────────────────────────────────────────────────────────────────

def _create_engine():
    """Create the SQLAlchemy engine with dialect-appropriate pool settings."""
    url = settings.database_url
    is_sqlite = url.startswith("sqlite")
    kwargs = {
        "echo": settings.api_debug,
    }
    if not is_sqlite:
        # Pool tuning only supported by server-based dialects
        kwargs.update({"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20})
    else:
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


engine = _create_engine()


@event.listens_for(engine, "connect")
def _on_connect(dbapi_conn, connection_record):  # noqa: ANN001
    """PostgreSQL: set search_path. SQLite: enable foreign keys."""
    if settings.database_url.startswith("postgresql"):
        cursor = dbapi_conn.cursor()
        cursor.execute("SET search_path TO public")
        cursor.close()
    elif settings.database_url.startswith("sqlite"):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")


# ── Session factory ───────────────────────────────────────────────────────────

SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# ── Base class for ORM models ─────────────────────────────────────────────────

class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# ── Helpers ───────────────────────────────────────────────────────────────────

@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Context-manager that provides a transactional database session.

    Automatically commits on success and rolls back on exception.

    Example::

        with get_session() as db:
            db.add(some_object)
    """
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session per HTTP request.

    Usage::

        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            ...
    """
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """
    Create all tables defined in the ORM models.

    Should be called once at application startup (e.g. in ``lifespan``).
    Safe to call multiple times – uses ``CREATE TABLE IF NOT EXISTS`` semantics
    via ``checkfirst=True``.
    """
    # Import models so SQLAlchemy registers them before ``create_all``
    from storage import models  # noqa: F401

    Base.metadata.create_all(bind=engine, checkfirst=True)
    logger.info("Database tables initialised.")


def health_check() -> bool:
    """Return True if the database is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("Database health-check failed: %s", exc)
        return False
