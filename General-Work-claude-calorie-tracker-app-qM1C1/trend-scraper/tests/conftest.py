"""
Shared pytest fixtures for the trend-scraper test suite.

Uses an in-memory SQLite database so tests run without a real PostgreSQL
instance.  The ORM models are database-agnostic (no PostgreSQL-specific
types in table definitions that SQLite can't handle).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

# ── Point settings at SQLite BEFORE any app module is imported ────────────────
import os
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from config.settings import get_settings

# Force the cached settings singleton to pick up the env override
get_settings.cache_clear()

from storage.db import Base, get_db
from storage.models import TrendItem, TrendScore
from ingestion.base import TrendItemSchema


# ── Session-scoped in-memory SQLite engine ────────────────────────────────────

TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine():
    """Session-scoped in-memory SQLite engine with all tables created."""
    eng = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(eng, "connect")
    def _enable_fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def db(engine):
    """
    Function-scoped session wrapped in a savepoint so each test is
    fully isolated and rolled back on teardown.
    """
    connection = engine.connect()
    transaction = connection.begin()
    TestSession = sessionmaker(bind=connection, autoflush=False)
    session = TestSession()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db):
    """FastAPI TestClient with the DB dependency overridden to the test session."""
    from api.main import app

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


# ── Sample data factories ─────────────────────────────────────────────────────

def make_trend_item(
    source: str = "reddit",
    title: str = "Test Post",
    raw_score: int = 100,
    **kwargs,
) -> TrendItem:
    """Return an unsaved TrendItem ORM object."""
    return TrendItem(
        id=uuid.uuid4(),
        source=source,
        title=title,
        raw_score=raw_score,
        timestamp=datetime.now(timezone.utc),
        metadata_=kwargs.get("metadata_", {}),
    )


def make_trend_schema(
    source: str = "reddit",
    title: str = "Test Post",
    raw_score: int = 100,
    **kwargs,
) -> TrendItemSchema:
    """Return a TrendItemSchema Pydantic object."""
    return TrendItemSchema(
        source=source,
        title=title,
        raw_score=raw_score,
        timestamp=datetime.now(timezone.utc),
        metadata=kwargs.get("metadata", {}),
    )
