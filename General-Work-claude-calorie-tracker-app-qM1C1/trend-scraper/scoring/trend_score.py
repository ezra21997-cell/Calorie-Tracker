"""
Trend scoring engine.

Formula
-------
::

    trend_score = (recent_mentions / max(baseline_mentions, 1)) * recency_weight

Where:
  - ``recent_mentions``   = number of items with the same title ingested in the
                            last ``recent_window_minutes`` minutes
  - ``baseline_mentions`` = rolling average count over the last
                            ``baseline_window_hours`` hours, computed per item
  - ``recency_weight``    = time-decay factor λ^(age_in_hours)

The scoring strategy is encapsulated behind a ``ScoringStrategy`` protocol so
it can be swapped (e.g. for an ML model) without touching ingestion or API code.

Public API
----------
``VelocityScoringStrategy``  – default implementation
``score_items(items, db)``   – convenience function using the default strategy
``ScoreResult``              – dataclass returned per scored item
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol, Sequence, runtime_checkable

from sqlalchemy import func
from sqlalchemy.orm import Session

from config.settings import get_settings
from storage.models import TrendItem, TrendScore
from utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class ScoreResult:
    """
    Holds the scoring output for a single trend item.

    Attributes:
        item_id:            UUID of the scored ``TrendItem``.
        title:              Item title (for convenience).
        source:             Source label.
        score:              Final normalised trend score.
        recent_mentions:    Mention count in the recent window.
        baseline_mentions:  Rolling baseline count.
        recency_weight:     Decay weight applied.
        scored_at:          UTC timestamp of this scoring run.
    """

    item_id: object
    title: str
    source: str
    score: float
    recent_mentions: int
    baseline_mentions: float
    recency_weight: float
    scored_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ── Strategy protocol (for dependency injection / swappability) ───────────────

@runtime_checkable
class ScoringStrategy(Protocol):
    """
    Protocol that any scoring strategy must implement.

    Implementing this protocol (duck-typing) is sufficient – no explicit
    subclassing required.
    """

    def score(
        self,
        items: Sequence[TrendItem],
        db: Session,
    ) -> list[ScoreResult]:
        """
        Compute scores for a list of ``TrendItem`` objects.

        Args:
            items: Items to score.
            db:    Active database session for historical queries.

        Returns:
            One ``ScoreResult`` per input item.
        """
        ...


# ── Default implementation ────────────────────────────────────────────────────

class VelocityScoringStrategy:
    """
    Velocity-based trend scoring.

    Scores are computed as::

        recency_weight = decay_lambda ^ age_in_hours
        trend_score    = (recent_mentions / max(baseline_mentions, 1))
                         * recency_weight

    A score > 1.0 indicates the item is trending above its baseline.
    A score close to 0 means it has gone quiet relative to history.

    Args:
        recent_window_minutes: Length of the "recent" window in minutes.
        baseline_window_hours: Hours used to compute the rolling baseline.
        decay_lambda:          Decay factor per hour (0 < λ ≤ 1).
                               Lower values penalise older items more harshly.
    """

    def __init__(
        self,
        recent_window_minutes: int | None = None,
        baseline_window_hours: int | None = None,
        decay_lambda: float | None = None,
    ) -> None:
        self.recent_window_minutes = (
            recent_window_minutes or settings.scoring_recent_window_minutes
        )
        self.baseline_window_hours = (
            baseline_window_hours or settings.scoring_baseline_window_hours
        )
        self.decay_lambda = decay_lambda or settings.scoring_recency_decay

    # ── Helpers ────────────────────────────────────────────────────────────

    def _recent_cutoff(self) -> datetime:
        return datetime.now(timezone.utc) - timedelta(
            minutes=self.recent_window_minutes
        )

    def _baseline_cutoff(self) -> datetime:
        return datetime.now(timezone.utc) - timedelta(
            hours=self.baseline_window_hours
        )

    def _recency_weight(self, item_timestamp: datetime) -> float:
        """
        Compute the exponential time-decay weight for an item.

        weight = λ ^ age_in_hours

        An item observed *now* gets weight 1.0; an item observed 1 hour ago
        gets weight λ; 2 hours ago → λ²; and so on.
        """
        now = datetime.now(timezone.utc)
        ts = item_timestamp.replace(tzinfo=timezone.utc) if item_timestamp.tzinfo is None else item_timestamp
        age_hours = max(0.0, (now - ts).total_seconds() / 3600)
        return math.pow(self.decay_lambda, age_hours)

    def _count_recent_mentions(
        self, title: str, source: str, db: Session
    ) -> int:
        """Count items with the same title+source in the recent window."""
        cutoff = self._recent_cutoff()
        return (
            db.query(func.count(TrendItem.id))
            .filter(
                TrendItem.title == title,
                TrendItem.source == source,
                TrendItem.timestamp >= cutoff,
            )
            .scalar()
            or 0
        )

    def _compute_baseline(
        self, title: str, source: str, db: Session
    ) -> float:
        """
        Compute the rolling baseline as the average hourly mention count
        over the baseline window.
        """
        cutoff = self._baseline_cutoff()
        total_count: int = (
            db.query(func.count(TrendItem.id))
            .filter(
                TrendItem.title == title,
                TrendItem.source == source,
                TrendItem.timestamp >= cutoff,
            )
            .scalar()
            or 0
        )
        # Average per hour within the window
        return total_count / max(self.baseline_window_hours, 1)

    # ── Main scoring method ────────────────────────────────────────────────

    def score(
        self,
        items: Sequence[TrendItem],
        db: Session,
    ) -> list[ScoreResult]:
        """
        Score all provided items.

        Args:
            items: ``TrendItem`` ORM objects to score.
            db:    Live database session.

        Returns:
            List of ``ScoreResult`` dataclasses, one per item.
        """
        results: list[ScoreResult] = []

        for item in items:
            recent = self._count_recent_mentions(item.title, item.source, db)
            baseline = self._compute_baseline(item.title, item.source, db)
            weight = self._recency_weight(item.timestamp)

            raw_score = (recent / max(baseline, 1.0)) * weight
            # Normalise to a 0–100 range (capped) for readability in the API
            normalised = min(raw_score * 10, 100.0)

            results.append(
                ScoreResult(
                    item_id=item.id,
                    title=item.title,
                    source=item.source,
                    score=round(normalised, 4),
                    recent_mentions=recent,
                    baseline_mentions=round(baseline, 4),
                    recency_weight=round(weight, 6),
                )
            )

        logger.debug("Scored %d items.", len(results))
        return results


# ── Persistence helper ────────────────────────────────────────────────────────

def persist_scores(results: list[ScoreResult], db: Session) -> list[TrendScore]:
    """
    Write ``ScoreResult`` objects to the ``trend_scores`` table.

    Each call appends new rows (history is preserved).

    Args:
        results: List of ``ScoreResult`` objects.
        db:      Active database session (caller manages commit).

    Returns:
        List of newly created ``TrendScore`` ORM instances.
    """
    orm_scores: list[TrendScore] = []
    for result in results:
        ts = TrendScore(
            item_id=result.item_id,
            score=result.score,
            recent_mentions=result.recent_mentions,
            baseline_mentions=result.baseline_mentions,
            recency_weight=result.recency_weight,
            scored_at=result.scored_at,
        )
        db.add(ts)
        orm_scores.append(ts)

    if orm_scores:
        db.flush()  # make rows visible within the same session/transaction

    logger.info("Persisted %d TrendScore rows.", len(orm_scores))
    return orm_scores


# ── Convenience entry-point ───────────────────────────────────────────────────

def score_items(
    items: Sequence[TrendItem],
    db: Session,
    *,
    strategy: ScoringStrategy | None = None,
    persist: bool = True,
) -> list[ScoreResult]:
    """
    Score items using *strategy* (defaults to ``VelocityScoringStrategy``).

    Args:
        items:    Items to score.
        db:       Active database session.
        strategy: Scoring strategy instance.  Defaults to velocity scoring.
        persist:  If True, write scores to the database.

    Returns:
        List of ``ScoreResult`` objects.
    """
    if strategy is None:
        strategy = VelocityScoringStrategy()

    results = strategy.score(items, db)

    if persist:
        persist_scores(results, db)

    return results
