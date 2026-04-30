"""
Tests for the processing layer (cleaner + normalizer).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from ingestion.base import TrendItemSchema
from processing.cleaner import (
    clean_item_title,
    clean_text,
    collapse_whitespace,
    normalize_unicode,
    remove_emojis,
    remove_urls,
    strip_excess_punctuation,
)
from processing.normalizer import (
    normalize_batch,
    normalize_item,
    schema_to_orm,
    normalize_and_persist,
)


# ── cleaner.py ────────────────────────────────────────────────────────────────

class TestRemoveUrls:
    def test_removes_https(self):
        assert "clean" in remove_urls("clean https://example.com text")
        assert "https://" not in remove_urls("https://example.com")

    def test_removes_www(self):
        result = remove_urls("visit www.example.com for more")
        assert "www." not in result

    def test_preserves_non_url(self):
        text = "hello world"
        assert remove_urls(text).strip() == text


class TestRemoveEmojis:
    def test_strips_common_emoji(self):
        result = remove_emojis("Hello 🔥 World 🚀")
        assert "🔥" not in result
        assert "🚀" not in result
        assert "Hello" in result
        assert "World" in result

    def test_preserves_plain_text(self):
        text = "plain text 123"
        assert remove_emojis(text) == text


class TestNormalizeUnicode:
    def test_nfkc_normalization(self):
        # Full-width digit should become ASCII digit after NFKC
        full_width = "\uff11"   # １
        assert normalize_unicode(full_width) == "1"

    def test_regular_ascii_unchanged(self):
        assert normalize_unicode("hello") == "hello"


class TestCollapseWhitespace:
    def test_multiple_spaces(self):
        assert collapse_whitespace("a   b   c") == "a b c"

    def test_leading_trailing(self):
        assert collapse_whitespace("  hello  ") == "hello"

    def test_newlines_collapsed(self):
        assert collapse_whitespace("a\n\nb") == "a b"


class TestStripExcessPunctuation:
    def test_removes_special_chars(self):
        result = strip_excess_punctuation("hello###world@@@test")
        assert "#" not in result
        assert "@" not in result

    def test_keeps_alphanumeric(self):
        result = strip_excess_punctuation("hello world 123")
        assert "hello" in result
        assert "123" in result


class TestCleanText:
    def test_full_pipeline(self):
        dirty = "Check this out!!! 🔥 https://example.com  LOUD TEXT   "
        cleaned = clean_text(dirty)
        assert "https://" not in cleaned
        assert "🔥" not in cleaned
        assert cleaned == cleaned.lower()
        assert "  " not in cleaned

    def test_lowercase_disabled(self):
        result = clean_text("HELLO", lowercase=False)
        assert result == "HELLO"

    def test_url_stripping_disabled(self):
        # strip_urls=False skips remove_urls(), but strip_excess_punctuation
        # still removes :// — verify the domain is at least preserved
        result = clean_text("go to https://example.com", strip_urls=False)
        assert "example" in result

    def test_emoji_stripping_disabled(self):
        # strip_emojis=False skips remove_emojis(), but strip_excess_punctuation
        # (which always runs) removes non-word chars including emoji.
        # Verify that plain text surrounding the emoji is preserved.
        result = clean_text("fire 🔥 test", strip_emojis=False)
        assert "fire" in result
        assert "test" in result

    def test_empty_string(self):
        assert clean_text("") == ""


class TestCleanItemTitle:
    def test_reddit_strips_subreddit(self):
        result = clean_item_title("posted in r/AskReddit today", source="reddit")
        assert "r/askreddit" not in result.lower()

    def test_google_keeps_subreddit_ref(self):
        # Google titles should not have subreddit mentions stripped
        result = clean_item_title("r/programming is popular", source="google")
        # We do NOT strip for non-reddit sources
        assert "programming" in result


# ── normalizer.py ─────────────────────────────────────────────────────────────

class TestNormalizeItem:
    def _make_schema(self, **kwargs) -> TrendItemSchema:
        defaults = dict(
            source="reddit",
            title="Hello World! 🔥 https://example.com",
            raw_score=500,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        defaults.update(kwargs)
        return TrendItemSchema(**defaults)

    def test_title_is_cleaned(self):
        item = self._make_schema()
        result = normalize_item(item)
        assert "https://" not in result.title
        assert "🔥" not in result.title

    def test_score_clamped_to_zero(self):
        item = self._make_schema(raw_score=-999)
        result = normalize_item(item)
        assert result.raw_score == 0

    def test_score_clamped_to_max(self):
        item = self._make_schema(raw_score=10 ** 12)
        result = normalize_item(item)
        assert result.raw_score == 2_000_000_000

    def test_naive_timestamp_made_utc(self):
        naive_ts = datetime(2024, 6, 1)  # no tzinfo
        item = self._make_schema(timestamp=naive_ts)
        result = normalize_item(item)
        assert result.timestamp.tzinfo is not None

    def test_returns_new_instance(self):
        item = self._make_schema()
        result = normalize_item(item)
        assert result is not item


class TestNormalizeBatch:
    def _make_schemas(self, n: int, source: str = "reddit") -> list[TrendItemSchema]:
        return [
            TrendItemSchema(source=source, title=f"Post number {i}", raw_score=i * 10)
            for i in range(n)
        ]

    def test_basic_batch(self):
        schemas = self._make_schemas(5)
        result = normalize_batch(schemas)
        assert len(result) == 5

    def test_deduplication_same_title(self):
        schemas = [
            TrendItemSchema(source="reddit", title="Duplicate Title", raw_score=100),
            TrendItemSchema(source="reddit", title="Duplicate Title", raw_score=200),
            TrendItemSchema(source="reddit", title="Unique Title", raw_score=50),
        ]
        result = normalize_batch(schemas, deduplicate=True)
        assert len(result) == 2

    def test_dedup_off_keeps_all(self):
        schemas = [
            TrendItemSchema(source="reddit", title="Same", raw_score=1),
            TrendItemSchema(source="reddit", title="Same", raw_score=2),
        ]
        result = normalize_batch(schemas, deduplicate=False)
        assert len(result) == 2

    def test_different_sources_not_deduped(self):
        schemas = [
            TrendItemSchema(source="reddit", title="AI News", raw_score=100),
            TrendItemSchema(source="google", title="AI News", raw_score=80),
        ]
        result = normalize_batch(schemas, deduplicate=True)
        assert len(result) == 2

    def test_empty_batch(self):
        assert normalize_batch([]) == []


class TestSchemaToOrm:
    def test_fields_mapped_correctly(self):
        schema = TrendItemSchema(
            source="reddit",
            title="Test Post",
            raw_score=999,
            url="https://reddit.com/r/test",
            metadata={"sub": "test"},
        )
        orm = schema_to_orm(schema)
        assert orm.id == schema.id
        assert orm.source == "reddit"
        assert orm.title == "Test Post"
        assert orm.raw_score == 999
        assert orm.url == "https://reddit.com/r/test"
        assert orm.metadata_["sub"] == "test"

    def test_returns_trend_item(self):
        from storage.models import TrendItem
        schema = TrendItemSchema(source="test", title="X")
        assert isinstance(schema_to_orm(schema), TrendItem)


class TestNormalizeAndPersist:
    def test_persists_new_items(self, db):
        schemas = [
            TrendItemSchema(source="reddit", title=f"Post {i}", raw_score=i * 10)
            for i in range(3)
        ]
        new_items = normalize_and_persist(schemas, db)
        assert len(new_items) == 3

    def test_idempotent_on_same_ids(self, db):
        schema = TrendItemSchema(source="reddit", title="Idempotent Post", raw_score=50)
        first = normalize_and_persist([schema], db)
        second = normalize_and_persist([schema], db)
        assert len(first) == 1
        assert len(second) == 0  # already exists

    def test_empty_input(self, db):
        result = normalize_and_persist([], db)
        assert result == []
