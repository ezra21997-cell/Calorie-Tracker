"""
Tests for the FastAPI routes layer.

Uses the ``client`` fixture from conftest.py which injects an
in-memory SQLite session so no real database is required.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from storage.models import TrendItem, TrendScore
from tests.conftest import make_trend_item


# ── /health ───────────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_response_shape(self, client):
        data = client.get("/health").json()
        assert "status" in data
        assert "database" in data
        assert "timestamp" in data

    def test_status_is_string(self, client):
        data = client.get("/health").json()
        assert isinstance(data["status"], str)


# ── /trends ───────────────────────────────────────────────────────────────────

class TestListTrends:
    def _seed(self, db, n: int = 5, source: str = "reddit") -> list[TrendItem]:
        items = [make_trend_item(source=source, title=f"Post {i}", raw_score=i * 10)
                 for i in range(n)]
        for item in items:
            db.add(item)
        db.flush()
        return items

    def test_empty_db_returns_empty_list(self, client):
        resp = client.get("/trends")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_returns_seeded_items(self, client, db):
        self._seed(db, n=3)
        resp = client.get("/trends")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

    def test_filter_by_source(self, client, db):
        self._seed(db, n=3, source="reddit")
        self._seed(db, n=2, source="google")

        resp = client.get("/trends?source=reddit")
        data = resp.json()
        assert data["total"] == 3
        assert all(i["source"] == "reddit" for i in data["items"])

    def test_filter_unknown_source_returns_empty(self, client, db):
        self._seed(db, n=3, source="reddit")
        resp = client.get("/trends?source=twitter")
        assert resp.json()["total"] == 0

    def test_pagination_page_size(self, client, db):
        self._seed(db, n=10)
        resp = client.get("/trends?page=1&page_size=3")
        data = resp.json()
        assert len(data["items"]) == 3
        assert data["total"] == 10
        assert data["page"] == 1
        assert data["page_size"] == 3

    def test_pagination_page_2(self, client, db):
        self._seed(db, n=10)
        resp = client.get("/trends?page=2&page_size=4")
        data = resp.json()
        assert len(data["items"]) == 4

    def test_item_schema_fields(self, client, db):
        self._seed(db, n=1)
        item = client.get("/trends").json()["items"][0]
        for field in ("id", "source", "title", "raw_score", "timestamp", "ingested_at"):
            assert field in item

    def test_invalid_page_returns_422(self, client):
        resp = client.get("/trends?page=0")
        assert resp.status_code == 422

    def test_page_size_above_max_returns_422(self, client):
        resp = client.get("/trends?page_size=999")
        assert resp.status_code == 422


# ── /trends/top ───────────────────────────────────────────────────────────────

class TestTopTrends:
    def _seed_with_scores(self, db, n: int = 5) -> list[TrendItem]:
        items = []
        for i in range(n):
            item = make_trend_item(title=f"Scored Post {i}", raw_score=i * 100)
            db.add(item)
            db.flush()
            score = TrendScore(
                item_id=item.id,
                score=float(i * 10),
                recent_mentions=i,
                baseline_mentions=1.0,
                recency_weight=0.9,
                scored_at=datetime.now(timezone.utc),
            )
            db.add(score)
            db.flush()
            items.append(item)
        return items

    def test_returns_top_n(self, client, db):
        self._seed_with_scores(db, n=10)
        resp = client.get("/trends/top?n=5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 5

    def test_top_sorted_by_score_descending(self, client, db):
        self._seed_with_scores(db, n=5)
        items = client.get("/trends/top?n=5").json()
        scores = [i["latest_score"] for i in items if i["latest_score"] is not None]
        assert scores == sorted(scores, reverse=True)

    def test_top_falls_back_to_raw_score_when_no_trend_scores(self, client, db):
        for i in range(5):
            item = make_trend_item(title=f"Unscored {i}", raw_score=i * 50)
            db.add(item)
        db.flush()
        resp = client.get("/trends/top?n=3")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_filter_by_source(self, client, db):
        for i in range(3):
            item = make_trend_item(source="reddit", title=f"Reddit {i}", raw_score=i)
            db.add(item)
        for i in range(2):
            item = make_trend_item(source="google", title=f"Google {i}", raw_score=i)
            db.add(item)
        db.flush()

        resp = client.get("/trends/top?n=10&source=reddit")
        data = resp.json()
        assert all(i["source"] == "reddit" for i in data)

    def test_n_above_max_returns_422(self, client):
        resp = client.get("/trends/top?n=200")
        assert resp.status_code == 422

    def test_empty_db_returns_empty_list(self, client):
        resp = client.get("/trends/top")
        assert resp.status_code == 200
        assert resp.json() == []


# ── /trends/{item_id} ─────────────────────────────────────────────────────────

class TestGetTrend:
    def test_returns_item(self, client, db):
        item = make_trend_item(title="Single Item", raw_score=777)
        db.add(item)
        db.flush()

        resp = client.get(f"/trends/{item.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(item.id)
        assert data["title"] == item.title

    def test_404_for_unknown_id(self, client):
        resp = client.get(f"/trends/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_invalid_uuid_returns_422(self, client):
        resp = client.get("/trends/not-a-uuid")
        assert resp.status_code == 422

    def test_includes_latest_score_when_present(self, client, db):
        item = make_trend_item(title="Scored Item")
        db.add(item)
        db.flush()

        score = TrendScore(
            item_id=item.id,
            score=55.5,
            recent_mentions=5,
            baseline_mentions=2.0,
            recency_weight=0.88,
            scored_at=datetime.now(timezone.utc),
        )
        db.add(score)
        db.flush()

        data = client.get(f"/trends/{item.id}").json()
        assert data["latest_score"] == pytest.approx(55.5)

    def test_latest_score_none_when_no_scores(self, client, db):
        item = make_trend_item(title="Unscored Item")
        db.add(item)
        db.flush()

        data = client.get(f"/trends/{item.id}").json()
        assert data["latest_score"] is None


# ── /trends (combined edge cases) ────────────────────────────────────────────

class TestEdgeCases:
    def test_metadata_returned_in_response(self, client, db):
        item = make_trend_item(title="Meta Post")
        item.metadata_ = {"subreddit": "worldnews", "author": "user42"}
        db.add(item)
        db.flush()

        data = client.get(f"/trends/{item.id}").json()
        assert data["metadata"]["subreddit"] == "worldnews"

    def test_url_field_nullable(self, client, db):
        item = make_trend_item(title="No URL Post")
        item.url = None
        db.add(item)
        db.flush()

        data = client.get(f"/trends/{item.id}").json()
        assert data["url"] is None
