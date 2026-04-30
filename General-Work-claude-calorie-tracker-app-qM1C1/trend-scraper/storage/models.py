"""
SQLAlchemy ORM models.

Tables
------
trend_items
    One row per raw item ingested from any data source.

trend_scores
    One row per scoring event.  A new row is written each time the
    scoring pipeline runs, so you retain a full history and can plot
    score evolution over time.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator, String as SAString
import uuid as _uuid_mod


class _CompatibleUUID(TypeDecorator):
    """UUID stored as CHAR(36) on SQLite, native UUID on PostgreSQL."""
    impl = SAString(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(SAString(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, _uuid_mod.UUID):
            return _uuid_mod.UUID(str(value))
        return value


class _CompatibleJSON(TypeDecorator):
    """JSONB on PostgreSQL, plain JSON elsewhere."""
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


# Aliases used in column definitions
UUID = _CompatibleUUID
_JSONB = _CompatibleJSON

from storage.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── TrendItem ─────────────────────────────────────────────────────────────────

class TrendItem(Base):
    """
    Represents a single piece of content ingested from a data source.

    Attributes:
        id:         UUID primary key.
        source:     Ingestion source label (e.g. ``"reddit"``, ``"google"``).
        title:      Human-readable title or keyword.
        raw_score:  Raw engagement number from the source
                    (upvotes, search volume, etc.).
        url:        Optional canonical URL for the item.
        timestamp:  When the item was published / observed at the source.
        ingested_at: When *we* first stored the item.
        metadata_:  Arbitrary JSON payload for source-specific fields.
        scores:     Back-reference to all ``TrendScore`` rows for this item.
    """

    __tablename__ = "trend_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    raw_score: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", _JSONB(), nullable=False, default=dict
    )

    scores: Mapped[list["TrendScore"]] = relationship(
        "TrendScore", back_populates="item", cascade="all, delete-orphan"
    )

    # Composite index for efficient source + time-range queries
    __table_args__ = (
        Index("ix_trend_items_source_timestamp", "source", "timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"<TrendItem id={self.id!s:.8} source={self.source!r} "
            f"title={self.title[:40]!r}>"
        )


# ── TrendScore ────────────────────────────────────────────────────────────────

class TrendScore(Base):
    """
    Stores the computed trend score for a ``TrendItem`` at a point in time.

    Keeping one row per scoring run (rather than updating in-place) lets you
    track how scores evolve – useful for charting velocity.

    Attributes:
        id:                 Auto-increment PK.
        item_id:            FK → ``trend_items.id``.
        score:              Final normalised trend score (0.0 – 1.0+ range).
        recent_mentions:    Count of mentions in the recent window.
        baseline_mentions:  Rolling baseline count for the same item.
        recency_weight:     Decay-adjusted weight applied during scoring.
        scored_at:          UTC timestamp of this scoring run.
        item:               ORM relationship back to the parent ``TrendItem``.
    """

    __tablename__ = "trend_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        ForeignKey("trend_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    recent_mentions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    baseline_mentions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    recency_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, index=True
    )

    item: Mapped[TrendItem] = relationship("TrendItem", back_populates="scores")

    __table_args__ = (
        Index("ix_trend_scores_item_scored_at", "item_id", "scored_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<TrendScore id={self.id} item_id={self.item_id!s:.8} "
            f"score={self.score:.4f}>"
        )
