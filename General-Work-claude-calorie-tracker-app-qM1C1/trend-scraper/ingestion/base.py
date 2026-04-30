"""
Abstract base class for all ingestion sources.

Every data-source adapter must subclass ``BaseIngester`` and implement
the three abstract methods:
  - ``fetch()``      – retrieve raw data from the external source
  - ``parse()``      – transform raw data into source-native dicts
  - ``normalize()``  – convert source-native dicts into ``TrendItemSchema``

This contract ensures all sources speak the same internal language and
can be used interchangeably by the processing and scoring pipelines.

Example (adding a new source)::

    from ingestion.base import BaseIngester, TrendItemSchema

    class HackerNewsIngester(BaseIngester):
        source_name = "hackernews"

        def fetch(self) -> list[dict]:
            ...

        def parse(self, raw: list[dict]) -> list[dict]:
            ...

        def normalize(self, parsed: list[dict]) -> list[TrendItemSchema]:
            ...
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


# ── Shared output schema ──────────────────────────────────────────────────────

class TrendItemSchema(BaseModel):
    """
    Canonical data model emitted by every ingestion source.

    All downstream layers (processing, scoring, storage) work exclusively
    with this schema, so new sources only need to implement ``normalize()``.

    Attributes:
        id:        UUID for deduplication / idempotency.
        source:    Lower-case source label (e.g. ``"reddit"``, ``"google"``).
        title:     Main text content – post title, keyword, headline.
        raw_score: Engagement signal from the source (upvotes, search volume).
        url:       Canonical URL (optional).
        timestamp: Publication / observation time (UTC-aware).
        metadata:  Source-specific supplementary data (subreddit, geo, …).
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source: str
    title: str
    raw_score: int = 0
    url: str | None = None
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": False}


# ── Abstract base ingester ────────────────────────────────────────────────────

class BaseIngester(ABC):
    """
    Abstract base class for data-source adapters.

    Subclasses must define ``source_name`` and implement the three abstract
    methods.  The ``run()`` convenience method chains them in order.

    Attributes:
        source_name: Unique string identifier for this source.
                     Used as the ``source`` field in ``TrendItemSchema``.
    """

    source_name: str = "unknown"

    @abstractmethod
    def fetch(self) -> Any:
        """
        Retrieve raw data from the external source.

        Returns:
            Any structure that ``parse()`` knows how to handle
            (HTTP response, list of dicts, raw bytes, etc.).

        Raises:
            IngestionError: On network or API failures.
        """

    @abstractmethod
    def parse(self, raw: Any) -> list[dict[str, Any]]:
        """
        Convert raw fetched data into a list of source-native dicts.

        Args:
            raw: The value returned by ``fetch()``.

        Returns:
            A list of plain dicts, one per item.
        """

    @abstractmethod
    def normalize(self, parsed: list[dict[str, Any]]) -> list[TrendItemSchema]:
        """
        Map source-native dicts to the canonical ``TrendItemSchema``.

        Args:
            parsed: The list returned by ``parse()``.

        Returns:
            A list of ``TrendItemSchema`` instances.
        """

    def run(self) -> list[TrendItemSchema]:
        """
        Execute the full ingestion pipeline: fetch → parse → normalize.

        Returns:
            A list of normalised ``TrendItemSchema`` items.
        """
        raw = self.fetch()
        parsed = self.parse(raw)
        return self.normalize(parsed)


# ── Exception ─────────────────────────────────────────────────────────────────

class IngestionError(RuntimeError):
    """Raised when an ingestion source fails to fetch or parse data."""
