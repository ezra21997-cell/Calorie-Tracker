"""
Background scheduler that drives the ingestion → processing → scoring pipeline.

Design
------
The scheduler is intentionally simple: a blocking loop with ``time.sleep``.
This makes it trivially deployable as a standalone process (``python -m
workers.scheduler``) or as a Docker container alongside the API.

For production scale, replace the loop body with a Celery/RQ task and
keep this file as the beat-scheduler configuration.

Pipeline per tick
-----------------
1. For each registered ingestion source:
   a. ``ingester.run()``                          → list[TrendItemSchema]
   b. ``normalize_and_persist(items, db)``        → list[TrendItem]
2. Score all items ingested in the last N minutes:
   ``score_items(recent_items, db)``
3. Commit the session.

Adding a new source
-------------------
Import your ingester and add it to ``_build_ingesters()``.
"""

from __future__ import annotations

import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.orm import Session

from config.settings import get_settings
from ingestion.base import BaseIngester, IngestionError, TrendItemSchema
from ingestion.google_trends import GoogleTrendsIngester
from ingestion.reddit import RedditIngester
from processing.normalizer import normalize_and_persist
from scoring.trend_score import score_items
from storage.db import get_session, init_db
from storage.models import TrendItem
from utils.logging import configure_logging, get_logger

settings = get_settings()
configure_logging(level=settings.log_level, use_json=settings.log_json)
logger = get_logger(__name__)

# ── Ingester registry ─────────────────────────────────────────────────────────


def _build_ingesters() -> list[BaseIngester]:
    """
    Return the list of active ingestion sources.

    To add a new source, instantiate it here and append to the list.
    """
    return [
        RedditIngester(),
        GoogleTrendsIngester(fetch_realtime_trends=True),
    ]


# ── Pipeline step helpers ─────────────────────────────────────────────────────


def _run_ingester(
    ingester: BaseIngester,
) -> list[TrendItemSchema]:
    """
    Run a single ingester, catching and logging errors so one failed
    source does not abort the whole pipeline.
    """
    try:
        items = ingester.run()
        logger.info(
            "Ingester '%s' collected %d items.", ingester.source_name, len(items)
        )
        return items
    except IngestionError as exc:
        logger.error("Ingester '%s' failed: %s", ingester.source_name, exc)
        return []
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unexpected error in ingester '%s': %s", ingester.source_name, exc
        )
        return []


def _score_recent(db: Session) -> None:
    """
    Score all items ingested within the recent window.

    Uses the same ``recent_window_minutes`` setting as the scoring engine
    so the two are always in sync.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=settings.scoring_recent_window_minutes
    )
    recent_items = (
        db.query(TrendItem).filter(TrendItem.ingested_at >= cutoff).all()
    )
    if not recent_items:
        logger.info("No recent items to score.")
        return

    score_items(recent_items, db, persist=True)
    logger.info("Scored %d recent items.", len(recent_items))


# ── Main pipeline tick ────────────────────────────────────────────────────────


def run_pipeline(ingesters: list[BaseIngester] | None = None) -> None:
    """
    Execute one full ingestion + scoring pipeline tick.

    Args:
        ingesters: Override the default ingester list (useful for tests).
    """
    if ingesters is None:
        ingesters = _build_ingesters()

    all_schemas: list[TrendItemSchema] = []
    for ingester in ingesters:
        all_schemas.extend(_run_ingester(ingester))

    if not all_schemas:
        logger.warning("No items ingested in this tick.")
        return

    with get_session() as db:
        new_items = normalize_and_persist(all_schemas, db)
        logger.info("Persisted %d new TrendItem rows.", len(new_items))
        _score_recent(db)

    logger.info("Pipeline tick complete.")


# ── Scheduler loop ────────────────────────────────────────────────────────────


def run_scheduler(
    interval_seconds: int | None = None,
    pipeline_fn: Callable[[], None] = run_pipeline,
    max_iterations: int | None = None,  # None = run forever; set for tests
) -> None:
    """
    Run the pipeline on a fixed interval loop.

    Args:
        interval_seconds: Sleep duration between ticks.
                          Defaults to ``settings.scheduler_interval_seconds``.
        pipeline_fn:      The pipeline callable to invoke each tick.
                          Swap out for testing.
        max_iterations:   Stop after this many iterations.  ``None`` = infinite.
    """
    interval = interval_seconds or settings.scheduler_interval_seconds
    logger.info(
        "Scheduler starting.  Interval: %d seconds (%d minutes).",
        interval,
        interval // 60,
    )

    # Graceful shutdown on SIGTERM / SIGINT
    _stop = {"flag": False}

    def _handle_signal(signum: int, _frame: object) -> None:  # noqa: ANN001
        logger.info("Received signal %d – stopping scheduler.", signum)
        _stop["flag"] = True

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    iterations = 0
    while not _stop["flag"]:
        tick_start = time.monotonic()
        logger.info("--- Scheduler tick #%d starting ---", iterations + 1)

        try:
            pipeline_fn()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled error during pipeline tick: %s", exc)

        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            break

        elapsed = time.monotonic() - tick_start
        sleep_for = max(0.0, interval - elapsed)
        logger.info(
            "Tick #%d done in %.1fs.  Next tick in %.0fs.",
            iterations,
            elapsed,
            sleep_for,
        )
        time.sleep(sleep_for)

    logger.info("Scheduler stopped after %d iterations.", iterations)


# ── Entry-point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    run_scheduler()
