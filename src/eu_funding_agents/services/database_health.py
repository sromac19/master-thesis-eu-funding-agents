import asyncio

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import literal

logger = structlog.get_logger(__name__)


class DatabaseUnavailableError(RuntimeError):
    pass


class DatabaseHealthService:
    def __init__(self, session: AsyncSession, *, timeout_seconds: float) -> None:
        self._session = session
        self._timeout_seconds = timeout_seconds

    async def check(self) -> None:
        try:
            await asyncio.wait_for(
                self._session.execute(select(literal(1))),
                timeout=self._timeout_seconds,
            )
        except Exception as exc:
            logger.warning("database_health_check_failed", error_type=type(exc).__name__)
            raise DatabaseUnavailableError from exc
