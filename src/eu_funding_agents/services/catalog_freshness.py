from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eu_funding_agents.db.models import FundingCall

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CatalogFreshness:
    last_fetched_at: datetime
    age_hours: float
    max_age_hours: int


class CatalogStaleError(RuntimeError):
    pass


class CatalogFreshnessService:
    def __init__(self, session: AsyncSession, *, max_age_hours: int) -> None:
        self._session = session
        self._max_age_hours = max_age_hours

    async def check(self, *, now: datetime | None = None) -> CatalogFreshness:
        last_fetched_at = await self._session.scalar(select(func.max(FundingCall.fetched_at)))
        if last_fetched_at is None:
            logger.warning("catalog_freshness_check_failed", reason="empty_catalog")
            raise CatalogStaleError("Catalog is empty")
        if last_fetched_at.tzinfo is None:
            logger.warning("catalog_freshness_check_failed", reason="naive_timestamp")
            raise CatalogStaleError("Catalog timestamp has no timezone")

        current_time = now or datetime.now(UTC)
        age_hours = max(0.0, (current_time - last_fetched_at).total_seconds() / 3600)
        freshness = CatalogFreshness(
            last_fetched_at=last_fetched_at,
            age_hours=age_hours,
            max_age_hours=self._max_age_hours,
        )
        if age_hours > self._max_age_hours:
            logger.warning(
                "catalog_freshness_check_failed",
                reason="stale_catalog",
                age_hours=age_hours,
                max_age_hours=self._max_age_hours,
            )
            raise CatalogStaleError("Catalog exceeds configured maximum age")
        return freshness
