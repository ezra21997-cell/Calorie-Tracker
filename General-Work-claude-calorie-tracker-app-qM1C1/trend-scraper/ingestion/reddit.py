"""
Reddit ingestion source.

Fetches the top posts from a configurable subreddit (default: r/all)
using the Reddit JSON API (no OAuth required for read-only public data).

For higher rate limits and private subreddit access, supply a
``REDDIT_CLIENT_ID`` / ``REDDIT_CLIENT_SECRET`` in the environment to
enable OAuth2 authentication via the ``/api/v1/access_token`` endpoint.

Environment variables
---------------------
REDDIT_CLIENT_ID      – OAuth2 app client ID (optional)
REDDIT_CLIENT_SECRET  – OAuth2 app client secret (optional)
REDDIT_USER_AGENT     – User-Agent header (required by Reddit ToS)
REDDIT_SUBREDDIT      – Subreddit to scrape (default: ``all``)
REDDIT_POST_LIMIT     – Max posts per fetch (default: 50, max: 100)
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx

from config.settings import get_settings
from ingestion.base import BaseIngester, IngestionError, TrendItemSchema
from utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_REDDIT_BASE = "https://www.reddit.com"
_OAUTH_BASE = "https://oauth.reddit.com"
_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"


class RedditIngester(BaseIngester):
    """
    Ingests top posts from a Reddit subreddit.

    Uses the public JSON API when no credentials are provided, or OAuth2
    when ``REDDIT_CLIENT_ID`` / ``REDDIT_CLIENT_SECRET`` are set.

    Args:
        subreddit:   Subreddit name (without ``r/``).
        post_limit:  Number of posts to retrieve per run (max 100).
        time_filter: Reddit listing time filter
                     (``hour``, ``day``, ``week``, ``month``, ``year``, ``all``).
    """

    source_name = "reddit"

    def __init__(
        self,
        subreddit: str | None = None,
        post_limit: int | None = None,
        time_filter: str = "hour",
    ) -> None:
        self.subreddit = subreddit or settings.reddit_subreddit
        self.post_limit = min(post_limit or settings.reddit_post_limit, 100)
        self.time_filter = time_filter
        self._token: str | None = None
        self._token_expiry: float = 0.0

    # ── OAuth2 helpers ─────────────────────────────────────────────────────

    def _has_credentials(self) -> bool:
        return bool(settings.reddit_client_id and settings.reddit_client_secret)

    def _get_access_token(self) -> str:
        """Fetch (or return a cached) OAuth2 access token."""
        if self._token and time.monotonic() < self._token_expiry:
            return self._token

        resp = httpx.post(
            _TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(settings.reddit_client_id, settings.reddit_client_secret),
            headers={"User-Agent": settings.reddit_user_agent},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = time.monotonic() + data.get("expires_in", 3600) - 60
        logger.debug("Reddit OAuth2 token refreshed.")
        return self._token  # type: ignore[return-value]

    # ── BaseIngester interface ─────────────────────────────────────────────

    def fetch(self) -> dict[str, Any]:
        """
        Call the Reddit ``/top.json`` endpoint.

        Returns:
            Parsed JSON response dict from Reddit's Listing API.

        Raises:
            IngestionError: On HTTP or connection failures.
        """
        params: dict[str, Any] = {
            "limit": self.post_limit,
            "t": self.time_filter,
        }
        headers = {"User-Agent": settings.reddit_user_agent}

        if self._has_credentials():
            token = self._get_access_token()
            headers["Authorization"] = f"Bearer {token}"
            url = f"{_OAUTH_BASE}/r/{self.subreddit}/top.json"
        else:
            url = f"{_REDDIT_BASE}/r/{self.subreddit}/top.json"

        logger.info(
            "Fetching Reddit top posts: subreddit=%s limit=%d t=%s",
            self.subreddit,
            self.post_limit,
            self.time_filter,
        )
        try:
            resp = httpx.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise IngestionError(
                f"Reddit API returned {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise IngestionError(f"Reddit request failed: {exc}") from exc

        return resp.json()  # type: ignore[return-value]

    def parse(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Extract the post list from Reddit's Listing wrapper.

        Args:
            raw: Full JSON response from the Reddit API.

        Returns:
            A list of Reddit post data dicts (``t3_`` items).
        """
        try:
            children = raw["data"]["children"]
        except (KeyError, TypeError) as exc:
            raise IngestionError(f"Unexpected Reddit response shape: {exc}") from exc

        posts = [child["data"] for child in children if child.get("kind") == "t3"]
        logger.debug("Reddit parsed %d posts.", len(posts))
        return posts

    def normalize(self, parsed: list[dict[str, Any]]) -> list[TrendItemSchema]:
        """
        Convert Reddit post dicts into canonical ``TrendItemSchema`` objects.

        Maps:
          - ``title``     → ``title``
          - ``score``     → ``raw_score``
          - ``created_utc`` → ``timestamp``
          - ``permalink`` → ``url``
          - ``subreddit``, ``author``, ``num_comments``, ``upvote_ratio``
            → ``metadata``

        Args:
            parsed: List of Reddit post dicts from ``parse()``.

        Returns:
            List of normalised ``TrendItemSchema`` items.
        """
        items: list[TrendItemSchema] = []
        for post in parsed:
            try:
                ts = datetime.fromtimestamp(
                    float(post["created_utc"]), tz=timezone.utc
                )
                items.append(
                    TrendItemSchema(
                        source=self.source_name,
                        title=post.get("title", ""),
                        raw_score=int(post.get("score", 0)),
                        url=f"https://www.reddit.com{post.get('permalink', '')}",
                        timestamp=ts,
                        metadata={
                            "subreddit": post.get("subreddit", ""),
                            "author": post.get("author", ""),
                            "num_comments": post.get("num_comments", 0),
                            "upvote_ratio": post.get("upvote_ratio", 0.0),
                            "is_self": post.get("is_self", False),
                            "domain": post.get("domain", ""),
                        },
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping Reddit post due to parse error: %s", exc)

        logger.info("Reddit normalised %d items.", len(items))
        return items
