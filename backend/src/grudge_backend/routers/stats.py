from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from grudge_backend.db import get_db
from grudge_backend.schemas.stats import LiveStatsRead
from grudge_backend.services import stats as stats_service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/live", response_model=LiveStatsRead)
async def get_live(db: AsyncSession = Depends(get_db)) -> LiveStatsRead:
    """Deliberately unauthenticated - the home page shows this to logged-out
    visitors too.
    """
    live = await stats_service.get_live_stats(db)
    return LiveStatsRead(online_count=live.online_count, in_activity_count=live.in_activity_count)
