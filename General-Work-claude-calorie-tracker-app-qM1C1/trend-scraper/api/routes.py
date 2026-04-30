"""
FastAPI route definitions for the trend-scraper API.

Endpoints
---------
GET  /health              – liveness check
GET  /trends              – list all trends (filterable by source)
GET  /trends/top          – top-N trends by score
GET  /trends/{item_id}    – retrieve a single trend item with its latest score
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from storage.db import get_db, health_check
from storage.models import TrendItem, TrendScore
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


# ── Response schemas ──────────────────────────────────────────────────────────

class TrendItemResponse(BaseModel):
    """Serialised representation of a single trend item."""

    id: uuid.UUID
    source: str
    title: str
    raw_score: int
    url: str | None
    timestamp: datetime
    ingested_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    latest_score: float | None = None

    model_config = {"from_attributes": True}


class TrendListResponse(BaseModel):
    """Paginated list of trend items."""

    total: int
    page: int
    page_size: int
    items: list[TrendItemResponse]


class HealthResponse(BaseModel):
    """API health-check response."""

    status: str
    database: bool
    timestamp: datetime


# ── Helpers ───────────────────────────────────────────────────────────────────

def _attach_latest_score(
    items: list[TrendItem], db: Session
) -> list[TrendItemResponse]:
    """
    Enrich a list of ORM items with their most recent ``TrendScore``.

    Uses a single subquery to avoid N+1 queries.
    """
    if not items:
        return []

    item_ids = [i.id for i in items]

    # Subquery: latest scored_at per item_id
    latest_sub = (
        db.query(
            TrendScore.item_id,
            func.max(TrendScore.scored_at).label("max_scored_at"),
        )
        .filter(TrendScore.item_id.in_(item_ids))
        .group_by(TrendScore.item_id)
        .subquery()
    )

    # Join to get score values
    score_rows = (
        db.query(TrendScore.item_id, TrendScore.score)
        .join(
            latest_sub,
            (TrendScore.item_id == latest_sub.c.item_id)
            & (TrendScore.scored_at == latest_sub.c.max_scored_at),
        )
        .all()
    )
    score_map: dict[uuid.UUID, float] = {row.item_id: row.score for row in score_rows}

    responses: list[TrendItemResponse] = []
    for item in items:
        responses.append(
            TrendItemResponse(
                id=item.id,
                source=item.source,
                title=item.title,
                raw_score=item.raw_score,
                url=item.url,
                timestamp=item.timestamp,
                ingested_at=item.ingested_at,
                metadata=item.metadata_,
                latest_score=score_map.get(item.id),
            )
        )
    return responses


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, tags=["Meta"])
def health() -> HealthResponse:
    """Liveness and readiness probe."""
    db_ok = health_check()
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        database=db_ok,
        timestamp=datetime.utcnow(),
    )


@router.get("/trends", response_model=TrendListResponse, tags=["Trends"])
def list_trends(
    source: Annotated[str | None, Query(description="Filter by source name")] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=200, description="Items per page")] = 50,
    db: Session = Depends(get_db),
) -> TrendListResponse:
    """
    Return all trend items ordered by ingestion time (newest first).

    Optional query parameters:
      - ``source``    – filter to a specific ingestion source (e.g. ``reddit``)
      - ``page``      – page index, starting at 1
      - ``page_size`` – number of results per page (max 200)
    """
    q = db.query(TrendItem)

    if source:
        q = q.filter(TrendItem.source == source.lower())

    total = q.count()
    items = (
        q.order_by(desc(TrendItem.ingested_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return TrendListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=_attach_latest_score(items, db),
    )


@router.get("/trends/top", response_model=list[TrendItemResponse], tags=["Trends"])
def top_trends(
    n: Annotated[int, Query(ge=1, le=100, description="Number of top trends")] = 10,
    source: Annotated[str | None, Query(description="Filter by source name")] = None,
    db: Session = Depends(get_db),
) -> list[TrendItemResponse]:
    """
    Return the top-N trend items ranked by their most recent score.

    If no scores exist yet (scheduler hasn't run), falls back to ranking
    by ``raw_score`` so the endpoint always returns useful data.

    Optional query parameters:
      - ``n``      – number of results (max 100)
      - ``source`` – filter by source
    """
    # Subquery: latest score per item
    latest_sub = (
        db.query(
            TrendScore.item_id,
            func.max(TrendScore.scored_at).label("max_scored_at"),
        )
        .group_by(TrendScore.item_id)
        .subquery()
    )

    score_sub = (
        db.query(TrendScore.item_id, TrendScore.score)
        .join(
            latest_sub,
            (TrendScore.item_id == latest_sub.c.item_id)
            & (TrendScore.scored_at == latest_sub.c.max_scored_at),
        )
        .subquery()
    )

    q = (
        db.query(TrendItem, score_sub.c.score)
        .outerjoin(score_sub, TrendItem.id == score_sub.c.item_id)
    )

    if source:
        q = q.filter(TrendItem.source == source.lower())

    rows = (
        q.order_by(
            desc(score_sub.c.score.is_(None)),  # items with scores first
            desc(score_sub.c.score),
            desc(TrendItem.raw_score),
        )
        .limit(n)
        .all()
    )

    responses: list[TrendItemResponse] = []
    for item, score in rows:
        responses.append(
            TrendItemResponse(
                id=item.id,
                source=item.source,
                title=item.title,
                raw_score=item.raw_score,
                url=item.url,
                timestamp=item.timestamp,
                ingested_at=item.ingested_at,
                metadata=item.metadata_,
                latest_score=score,
            )
        )
    return responses


@router.get(
    "/trends/{item_id}",
    response_model=TrendItemResponse,
    tags=["Trends"],
)
def get_trend(
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> TrendItemResponse:
    """Retrieve a single trend item and its latest score by UUID."""
    item = db.query(TrendItem).filter(TrendItem.id == item_id).first()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TrendItem {item_id} not found.",
        )
    return _attach_latest_score([item], db)[0]
