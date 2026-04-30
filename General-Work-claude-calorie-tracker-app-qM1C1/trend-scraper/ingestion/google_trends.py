"""
Google Trends ingestion source.

Uses ``pytrends`` (an unofficial Google Trends API wrapper) to fetch
currently trending searches and keyword interest over time.

Two modes of operation
----------------------
1. **Realtime trending searches** (``fetch_realtime_trends=True``)
   Returns keywords that are trending *right now* in a given geography.

2. **Interest over time** (``keywords`` list provided)
   Returns relative search interest (0–100) for specific keywords
   over a rolling time window.

Environment variables
---------------------
GOOGLE_TRENDS_GEO   – ISO 3166-1 alpha-2 country code, e.g. ``"US"``
                      (empty string = worldwide)
GOOGLE_TRENDS_HL    – Language for results, e.g. ``"en-US"``
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from config.settings import get_settings
from ingestion.base import BaseIngester, IngestionError, TrendItemSchema
from utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class GoogleTrendsIngester(BaseIngester):
    """
    Ingests trending search data from Google Trends via ``pytrends``.

    Args:
        geo:                  Geography filter (ISO 3166-1 alpha-2 or ``""``).
        hl:                   Host language for results.
        fetch_realtime_trends: When True, fetch real-time trending searches.
        keywords:             Optional keyword list for interest-over-time mode.
        timeframe:            pytrends timeframe string (e.g. ``"now 1-H"``).
    """

    source_name = "google"

    def __init__(
        self,
        geo: str | None = None,
        hl: str | None = None,
        fetch_realtime_trends: bool = True,
        keywords: list[str] | None = None,
        timeframe: str = "now 1-H",
    ) -> None:
        self.geo = geo if geo is not None else settings.google_trends_geo
        self.hl = hl or settings.google_trends_hl
        self.fetch_realtime_trends = fetch_realtime_trends
        self.keywords = keywords or []
        self.timeframe = timeframe
        self._pytrends: Any = None  # lazy-initialised

    # ── pytrends initialisation ────────────────────────────────────────────

    def _get_pytrends(self) -> Any:
        """Lazily create a pytrends ``TrendReq`` instance."""
        if self._pytrends is None:
            try:
                from pytrends.request import TrendReq  # type: ignore[import]
            except ImportError as exc:
                raise IngestionError(
                    "pytrends is not installed.  "
                    "Run: pip install pytrends"
                ) from exc
            self._pytrends = TrendReq(hl=self.hl, tz=0, timeout=(10, 25))
        return self._pytrends

    # ── BaseIngester interface ─────────────────────────────────────────────

    def fetch(self) -> list[dict[str, Any]]:
        """
        Retrieve trend data from Google Trends.

        Returns:
            A list of raw dicts representing trending topics or keyword stats.

        Raises:
            IngestionError: On network or parsing failures.
        """
        pt = self._get_pytrends()

        if self.fetch_realtime_trends:
            return self._fetch_realtime(pt)
        return self._fetch_interest_over_time(pt)

    def _fetch_realtime(self, pt: Any) -> list[dict[str, Any]]:
        """Fetch real-time trending searches for the configured geography."""
        geo = self.geo or "US"  # pytrends realtime requires a non-empty geo
        logger.info("Fetching Google Trends real-time searches: geo=%s", geo)
        try:
            df = pt.realtime_trending_searches(pn=geo)
        except Exception as exc:
            raise IngestionError(
                f"Google Trends realtime fetch failed: {exc}"
            ) from exc

        if df is None or df.empty:
            logger.warning("Google Trends returned an empty real-time dataframe.")
            return []

        return df.to_dict(orient="records")  # type: ignore[return-value]

    def _fetch_interest_over_time(self, pt: Any) -> list[dict[str, Any]]:
        """Fetch interest-over-time for a list of keywords."""
        if not self.keywords:
            logger.warning("No keywords provided for Google Trends interest query.")
            return []

        # pytrends accepts at most 5 keywords per request
        kw_chunk = self.keywords[:5]
        logger.info(
            "Fetching Google Trends interest-over-time: keywords=%s timeframe=%s",
            kw_chunk,
            self.timeframe,
        )
        try:
            pt.build_payload(kw_chunk, timeframe=self.timeframe, geo=self.geo)
            df = pt.interest_over_time()
        except Exception as exc:
            raise IngestionError(
                f"Google Trends interest-over-time fetch failed: {exc}"
            ) from exc

        if df is None or df.empty:
            logger.warning("Google Trends returned an empty interest dataframe.")
            return []

        # Melt wide format into long format for uniform downstream handling
        df = df.drop(columns=["isPartial"], errors="ignore").reset_index()
        melted = df.melt(id_vars=["date"], var_name="keyword", value_name="value")
        return melted.to_dict(orient="records")  # type: ignore[return-value]

    def parse(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Pass raw records through – they are already dicts from pandas.

        Args:
            raw: List of dicts from ``fetch()``.

        Returns:
            Same list unchanged.
        """
        return raw

    def normalize(self, parsed: list[dict[str, Any]]) -> list[TrendItemSchema]:
        """
        Convert Google Trends dicts into canonical ``TrendItemSchema`` objects.

        Handles both realtime-trending and interest-over-time record shapes.

        Args:
            parsed: List of dicts from ``parse()``.

        Returns:
            List of normalised ``TrendItemSchema`` items.
        """
        items: list[TrendItemSchema] = []
        now = datetime.now(timezone.utc)

        for record in parsed:
            try:
                if self.fetch_realtime_trends:
                    # Realtime schema: title, entityNames, formattedTraffic, …
                    title = (
                        record.get("title")
                        or record.get("entityNames")
                        or str(record)
                    )
                    if isinstance(title, list):
                        title = ", ".join(str(t) for t in title)
                    traffic_raw = record.get("formattedTraffic", "0+")
                    # Strip non-numeric chars from e.g. "200K+"
                    traffic_str = (
                        str(traffic_raw)
                        .replace(",", "")
                        .replace("+", "")
                        .replace("K", "000")
                        .replace("M", "000000")
                    )
                    try:
                        raw_score = int(float(traffic_str))
                    except (ValueError, TypeError):
                        raw_score = 0

                    ts = now
                    meta: dict[str, Any] = {
                        "entity_names": record.get("entityNames", []),
                        "articles": record.get("articles", []),
                    }
                else:
                    # Interest-over-time schema: date, keyword, value
                    title = str(record.get("keyword", ""))
                    raw_score = int(record.get("value", 0))
                    date_val = record.get("date")
                    if isinstance(date_val, datetime):
                        ts = date_val.replace(tzinfo=timezone.utc)
                    else:
                        ts = now
                    meta = {"timeframe": self.timeframe, "geo": self.geo}

                items.append(
                    TrendItemSchema(
                        source=self.source_name,
                        title=title,
                        raw_score=raw_score,
                        timestamp=ts,
                        metadata=meta,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping Google Trends record: %s", exc)

        logger.info("Google Trends normalised %d items.", len(items))
        return items
