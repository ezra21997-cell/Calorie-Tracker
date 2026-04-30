"""
Normalisation layer – converts ``TrendItemSchema`` objects (from ingestion)
into ``TrendItem`` ORM models ready for persistence.

Responsibilities
----------------
- Apply text cleaning via ``cleaner.clean_item_title``
- Clamp / validate ``raw_score`` to a safe integer range
- Ensure ``timestamp`` is always UTC-aware
- Deduplicate within a batch by (source, title) fingerprint

Public API
----------
``normalize_item(item)``          – process a single schema object
``normalize_batch(items)``        – process a list, with deduplication
``schema_to_orm(item)``           – convert schema → ORM model (no clean)
``normalize_and_persist(items, db)`` – full pipeline: clean → dedup → save
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy.orm import Session

from ingestion.base import TrendItemSchema
from processing.cleaner import clean_item_title
from storage.models import TrendItem
from utils.logging import get_logger

logger = get_logger(__name__)

_MAX_RAW_SCORE = 2_000_000_000  # guard against overflow


# ── Core normalisation helpers ────────────────────────────────────────────────

def _ensure_utc(dt: datetime) -> datetime:
    """Return a UTC-aware datetime, assuming UTC if naive."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _item_fingerprint(source: str, title: str) -> str:
    """Return a short hex fingerprint used for within-batch deduplication."""
    raw = f"{source.lower()}|{title.lower()}"
    return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()


# ── Single-item normalisation ─────────────────────────────────────────────────

def normalize_item(item: TrendItemSchema) -> TrendItemSchema:
    """
    Apply cleaning and validation rules to a single ``TrendItemSchema``.

    Mutations applied (returns a new instance):
      - ``title``     → cleaned via ``clean_item_title``
      - ``raw_score`` → clamped to [0, _MAX_RAW_SCORE]
      - ``timestamp`` → made UTC-aware

    Args:
        item: Raw schema object from an ingestion source.

    Returns:
        A new ``TrendItemSchema`` with normalised fields.
    """
    cleaned_title = clean_item_title(item.title, source=item.source)
    clamped_score = max(0, min(int(item.raw_score), _MAX_RAW_SCORE))
    aware_ts = _ensure_utc(item.timestamp)

    return item.model_copy(
        update={
            "title": cleaned_title,
            "raw_score": clamped_score,
            "timestamp": aware_ts,
        }
    )


# ── Batch normalisation with deduplication ────────────────────────────────────

def normalize_batch(
    items: Sequence[TrendItemSchema],
    *,
    deduplicate: bool = True,
) -> list[TrendItemSchema]:
    """
    Normalise a list of ``TrendItemSchema`` objects.

    Args:
        items:       Input schemas from one or more ingestion sources.
        deduplicate: When True, discard within-batch duplicates
                     (same source + cleaned title).

    Returns:
        List of normalised schemas.
    """
    seen: set[str] = set()
    result: list[TrendItemSchema] = []

    for item in items:
        normalised = normalize_item(item)

        if deduplicate:
            fp = _item_fingerprint(normalised.source, normalised.title)
            if fp in seen:
                logger.debug(
                    "Dedup: skipping duplicate '%s' from %s",
                    normalised.title[:60],
                    normalised.source,
                )
                continue
            seen.add(fp)

        result.append(normalised)

    logger.info(
        "Normalised batch: %d in → %d out (dedup=%s)",
        len(items),
        len(result),
        deduplicate,
    )
    return result


# ── Schema → ORM conversion ───────────────────────────────────────────────────

def schema_to_orm(item: TrendItemSchema) -> TrendItem:
    """
    Convert a ``TrendItemSchema`` to a ``TrendItem`` ORM model.

    Does *not* perform any additional cleaning – call ``normalize_item``
    first if needed.

    Args:
        item: Normalised schema object.

    Returns:
        An unsaved ``TrendItem`` ORM instance.
    """
    return TrendItem(
        id=item.id,
        source=item.source,
        title=item.title,
        raw_score=item.raw_score,
        url=item.url,
        timestamp=item.timestamp,
        metadata_=item.metadata,
    )


# ── Full pipeline helper ──────────────────────────────────────────────────────

def normalize_and_persist(
    items: Sequence[TrendItemSchema],
    db: Session,
    *,
    deduplicate: bool = True,
) -> list[TrendItem]:
    """
    Clean, deduplicate, and persist a batch of trend items.

    Existing rows (matched by ``id``) are skipped to maintain idempotency.

    Args:
        items:       Raw schemas from ingestion.
        db:          Active SQLAlchemy session (caller manages commit).
        deduplicate: Pass-through to ``normalize_batch``.

    Returns:
        List of newly inserted ``TrendItem`` ORM objects.
    """
    normalised = normalize_batch(items, deduplicate=deduplicate)

    existing_ids = {
        row.id
        for row in db.query(TrendItem.id)
        .filter(TrendItem.id.in_([i.id for i in normalised]))
        .all()
    }

    new_items: list[TrendItem] = []
    for schema in normalised:
        if schema.id in existing_ids:
            continue
        orm_item = schema_to_orm(schema)
        db.add(orm_item)
        new_items.append(orm_item)

    if new_items:
        db.flush()  # make rows visible within the same session/transaction

    logger.info("Persisted %d new TrendItem rows.", len(new_items))
    return new_items
