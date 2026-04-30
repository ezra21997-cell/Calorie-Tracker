"""
Tests for the scoring layer (trend_score.py).
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from scoring.trend_score import (
    ScoreResult,
    VelocityScoringStrategy,
    persist_scores,
    score_items,
)
from storage.models import TrendItem, TrendScore
from tests.conftest import make_trend_item


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _persist_item(db, item: TrendItem) -> TrendItem:
    db.add(item)
    db.flush()
    return item


# ── VelocityScoringStrategy ───────────────────────────────────────────────────

class TestRecencyWeight:
    def setup_method(self):
        self.strategy = VelocityScoringStrategy(
            recent_window_minutes=60,
            baseline_window_hours=24,
            decay_lambda=0.9,
        )

    def test_brand_new_item_weight_is_one(self):
        ts = _utcnow()
        weight = self.strategy._recency_weight(ts)
        assert abs(weight - 1.0) < 0.01   # nearly 1.0

    def test_one_hour_old_item(self):
        ts = _utcnow() - timedelta(hours=1)
        weight = self.strategy._recency_weight(ts)
        assert abs(weight - 0.9) < 0.05

    def test_older_items_have_lower_weight(self):
        fresh = self.strategy._recency_weight(_utcnow())
        old = self.strategy._recency_weight(_utcnow() - timedelta(hours=5))
        assert fresh > old

    def test_weight_never_below_zero(self):
        very_old = _utcnow() - timedelta(days=365)
        weight = self.strategy._recency_weight(very_old)
        assert weight >= 0.0

    def test_naive_timestamp_handled(self):
        naive = datetime(2024, 1, 1)   # no tzinfo
        weight = self.strategy._recency_weight(naive)
        assert weight >= 0.0


class TestCountRecentMentions:
    def test_counts_within_window(self, db):
        strategy = VelocityScoringStrategy(recent_window_minutes=60)
        recent_ts = _utcnow() - timedelta(minutes=30)
        old_ts = _utcnow() - timedelta(hours=3)

        recent_item = make_trend_item(source="reddit", title="hot topic")
        recent_item.timestamp = recent_ts
        old_item = make_trend_item(source="reddit", title="hot topic")
        old_item.timestamp = old_ts

        db.add(recent_item)
        db.add(old_item)
        db.flush()

        count = strategy._count_recent_mentions("hot topic", "reddit", db)
        assert count == 1   # only the recent one

    def test_returns_zero_when_none(self, db):
        strategy = VelocityScoringStrategy()
        count = strategy._count_recent_mentions("ghost keyword", "reddit", db)
        assert count == 0


class TestComputeBaseline:
    def test_baseline_averages_over_window(self, db):
        strategy = VelocityScoringStrategy(baseline_window_hours=24)

        # Insert 24 items spread over the last 24 hours → avg ≈ 1 per hour
        for i in range(24):
            item = make_trend_item(source="google", title="steady trend")
            item.timestamp = _utcnow() - timedelta(hours=i)
            db.add(item)
        db.flush()

        baseline = strategy._compute_baseline("steady trend", "google", db)
        assert abs(baseline - 1.0) < 0.2

    def test_baseline_zero_for_unknown(self, db):
        strategy = VelocityScoringStrategy()
        result = strategy._compute_baseline("unknown term", "reddit", db)
        assert result == 0.0


class TestVelocityScoringStrategyScore:
    def test_trending_item_scores_above_baseline(self, db):
        """
        Insert many recent mentions and few old ones so the item
        scores above the baseline (score > some_threshold).
        """
        strategy = VelocityScoringStrategy(
            recent_window_minutes=60,
            baseline_window_hours=24,
            decay_lambda=0.95,
        )

        # Baseline: 1 item per hour over past 24 hours
        for i in range(1, 25):
            old = make_trend_item(source="reddit", title="viral post")
            old.timestamp = _utcnow() - timedelta(hours=i)
            db.add(old)

        # Recent spike: 10 items in the last 30 minutes
        for _ in range(10):
            recent = make_trend_item(source="reddit", title="viral post")
            recent.timestamp = _utcnow() - timedelta(minutes=15)
            db.add(recent)

        # The item to score
        target = make_trend_item(source="reddit", title="viral post")
        target.timestamp = _utcnow() - timedelta(minutes=5)
        db.add(target)
        db.flush()

        results = strategy.score([target], db)
        assert len(results) == 1
        assert results[0].score > 1.0   # above baseline

    def test_cold_item_scores_low(self, db):
        strategy = VelocityScoringStrategy(
            recent_window_minutes=60,
            baseline_window_hours=24,
            decay_lambda=0.9,
        )
        old_item = make_trend_item(source="reddit", title="forgotten post")
        old_item.timestamp = _utcnow() - timedelta(hours=10)
        db.add(old_item)
        db.flush()

        results = strategy.score([old_item], db)
        assert results[0].score < 5.0

    def test_empty_items_returns_empty(self, db):
        strategy = VelocityScoringStrategy()
        assert strategy.score([], db) == []

    def test_score_result_fields(self, db):
        strategy = VelocityScoringStrategy()
        item = make_trend_item(source="reddit", title="check fields")
        db.add(item)
        db.flush()

        results = strategy.score([item], db)
        r = results[0]
        assert r.item_id == item.id
        assert r.title == item.title
        assert r.source == item.source
        assert isinstance(r.score, float)
        assert isinstance(r.recent_mentions, int)
        assert isinstance(r.recency_weight, float)
        assert isinstance(r.scored_at, datetime)


# ── persist_scores ────────────────────────────────────────────────────────────

class TestPersistScores:
    def test_writes_trend_score_rows(self, db):
        item = make_trend_item()
        db.add(item)
        db.flush()

        result = ScoreResult(
            item_id=item.id,
            title=item.title,
            source=item.source,
            score=42.5,
            recent_mentions=3,
            baseline_mentions=1.0,
            recency_weight=0.95,
        )
        orm_scores = persist_scores([result], db)
        assert len(orm_scores) == 1
        assert orm_scores[0].score == 42.5
        assert orm_scores[0].item_id == item.id

    def test_multiple_scores_per_item(self, db):
        item = make_trend_item()
        db.add(item)
        db.flush()

        results = [
            ScoreResult(
                item_id=item.id,
                title=item.title,
                source=item.source,
                score=float(i),
                recent_mentions=i,
                baseline_mentions=1.0,
                recency_weight=0.9,
            )
            for i in range(3)
        ]
        orm_scores = persist_scores(results, db)
        assert len(orm_scores) == 3

    def test_empty_list(self, db):
        assert persist_scores([], db) == []


# ── score_items convenience function ─────────────────────────────────────────

class TestScoreItems:
    def test_returns_score_results(self, db):
        items = [make_trend_item(title=f"item {i}") for i in range(3)]
        for i in items:
            db.add(i)
        db.flush()

        results = score_items(items, db, persist=False)
        assert len(results) == 3
        assert all(isinstance(r, ScoreResult) for r in results)

    def test_persist_true_writes_to_db(self, db):
        item = make_trend_item(title="persist me")
        db.add(item)
        db.flush()

        score_items([item], db, persist=True)
        count = db.query(TrendScore).filter(TrendScore.item_id == item.id).count()
        assert count == 1

    def test_custom_strategy_used(self, db):
        item = make_trend_item()
        db.add(item)
        db.flush()

        class FakeStrategy:
            def score(self, items, db):
                return [
                    ScoreResult(
                        item_id=i.id,
                        title=i.title,
                        source=i.source,
                        score=99.9,
                        recent_mentions=0,
                        baseline_mentions=0.0,
                        recency_weight=1.0,
                    )
                    for i in items
                ]

        results = score_items([item], db, strategy=FakeStrategy(), persist=False)
        assert results[0].score == 99.9
