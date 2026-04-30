"""
Tests for the ingestion layer.

Covers:
  - BaseIngester contract
  - RedditIngester fetch / parse / normalize
  - GoogleTrendsIngester normalize (both modes)
  - TrendItemSchema field validation
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from ingestion.base import BaseIngester, IngestionError, TrendItemSchema
from ingestion.reddit import RedditIngester
from ingestion.google_trends import GoogleTrendsIngester


# ── TrendItemSchema ───────────────────────────────────────────────────────────

class TestTrendItemSchema:
    def test_defaults(self):
        item = TrendItemSchema(source="test", title="Hello")
        assert isinstance(item.id, uuid.UUID)
        assert item.raw_score == 0
        assert item.url is None
        assert isinstance(item.timestamp, datetime)
        assert item.metadata == {}

    def test_all_fields(self):
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        item = TrendItemSchema(
            source="reddit",
            title="Big Post",
            raw_score=9999,
            url="https://reddit.com/r/all",
            timestamp=ts,
            metadata={"sub": "all"},
        )
        assert item.source == "reddit"
        assert item.raw_score == 9999
        assert item.timestamp == ts


# ── BaseIngester (abstract contract) ─────────────────────────────────────────

class ConcreteIngester(BaseIngester):
    source_name = "test_source"

    def fetch(self):
        return [{"key": "value"}]

    def parse(self, raw):
        return raw

    def normalize(self, parsed):
        return [
            TrendItemSchema(source=self.source_name, title=str(p))
            for p in parsed
        ]


class TestBaseIngester:
    def test_run_chains_methods(self):
        ingester = ConcreteIngester()
        results = ingester.run()
        assert len(results) == 1
        assert results[0].source == "test_source"

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BaseIngester()  # type: ignore


# ── RedditIngester ────────────────────────────────────────────────────────────

REDDIT_FIXTURE = {
    "data": {
        "children": [
            {
                "kind": "t3",
                "data": {
                    "title": "Example Reddit Post",
                    "score": 42000,
                    "subreddit": "worldnews",
                    "author": "user123",
                    "created_utc": 1_700_000_000.0,
                    "permalink": "/r/worldnews/comments/abc/",
                    "num_comments": 512,
                    "upvote_ratio": 0.95,
                    "is_self": False,
                    "domain": "reuters.com",
                },
            },
            {
                "kind": "t3",
                "data": {
                    "title": "Another Post",
                    "score": 100,
                    "subreddit": "funny",
                    "author": "joker",
                    "created_utc": 1_700_001_000.0,
                    "permalink": "/r/funny/comments/xyz/",
                    "num_comments": 10,
                    "upvote_ratio": 0.80,
                    "is_self": True,
                    "domain": "self.funny",
                },
            },
            # Non-t3 kind should be skipped
            {"kind": "t2", "data": {"name": "some user"}},
        ]
    }
}


class TestRedditIngester:
    def setup_method(self):
        self.ingester = RedditIngester(subreddit="all", post_limit=25)

    def test_parse_extracts_t3_only(self):
        posts = self.ingester.parse(REDDIT_FIXTURE)
        assert len(posts) == 2
        assert posts[0]["title"] == "Example Reddit Post"

    def test_parse_bad_shape_raises(self):
        with pytest.raises(IngestionError):
            self.ingester.parse({"bad": "shape"})

    def test_normalize_returns_schema_objects(self):
        posts = self.ingester.parse(REDDIT_FIXTURE)
        items = self.ingester.normalize(posts)
        assert len(items) == 2
        first = items[0]
        assert isinstance(first, TrendItemSchema)
        assert first.source == "reddit"
        assert first.title == "Example Reddit Post"
        assert first.raw_score == 42000
        assert "reddit.com" in first.url
        assert first.metadata["subreddit"] == "worldnews"
        assert first.metadata["num_comments"] == 512

    def test_normalize_timestamp_utc(self):
        posts = self.ingester.parse(REDDIT_FIXTURE)
        items = self.ingester.normalize(posts)
        assert items[0].timestamp.tzinfo is not None

    @patch("ingestion.reddit.httpx.get")
    def test_fetch_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = REDDIT_FIXTURE
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        result = self.ingester.fetch()
        assert "data" in result

    @patch("ingestion.reddit.httpx.get")
    def test_fetch_http_error_raises_ingestion_error(self, mock_get):
        import httpx

        mock_get.side_effect = httpx.RequestError("timeout")
        with pytest.raises(IngestionError, match="Reddit request failed"):
            self.ingester.fetch()

    def test_full_run(self):
        with patch.object(self.ingester, "fetch", return_value=REDDIT_FIXTURE):
            items = self.ingester.run()
        assert len(items) == 2
        assert all(isinstance(i, TrendItemSchema) for i in items)


# ── GoogleTrendsIngester ──────────────────────────────────────────────────────

GOOGLE_REALTIME_FIXTURE = [
    {
        "title": "Trending Topic",
        "entityNames": ["Entity A"],
        "formattedTraffic": "500K+",
        "articles": [],
    },
    {
        "title": "Another Trend",
        "entityNames": ["Entity B"],
        "formattedTraffic": "200K+",
        "articles": [],
    },
]

GOOGLE_INTEREST_FIXTURE = [
    {"date": datetime(2024, 1, 1, tzinfo=timezone.utc), "keyword": "python", "value": 72},
    {"date": datetime(2024, 1, 1, tzinfo=timezone.utc), "keyword": "rust", "value": 45},
]


class TestGoogleTrendsIngester:
    def test_normalize_realtime(self):
        ingester = GoogleTrendsIngester(fetch_realtime_trends=True)
        items = ingester.normalize(GOOGLE_REALTIME_FIXTURE)
        assert len(items) == 2
        assert items[0].source == "google"
        assert items[0].title == "Trending Topic"
        assert items[0].raw_score == 500_000

    def test_normalize_interest_over_time(self):
        ingester = GoogleTrendsIngester(
            fetch_realtime_trends=False, keywords=["python", "rust"]
        )
        items = ingester.normalize(GOOGLE_INTEREST_FIXTURE)
        assert len(items) == 2
        assert items[0].title == "python"
        assert items[0].raw_score == 72

    def test_parse_is_passthrough(self):
        ingester = GoogleTrendsIngester()
        data = [{"a": 1}]
        assert ingester.parse(data) == data

    def test_normalize_empty(self):
        ingester = GoogleTrendsIngester()
        assert ingester.normalize([]) == []

    def test_fetch_raises_without_pytrends(self):
        ingester = GoogleTrendsIngester(fetch_realtime_trends=True)
        with patch.dict("sys.modules", {"pytrends": None, "pytrends.request": None}):
            # Force lazy init to fail
            ingester._pytrends = None
            with pytest.raises(IngestionError, match="pytrends is not installed"):
                ingester.fetch()
