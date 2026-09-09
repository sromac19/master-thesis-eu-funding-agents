from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from eu_funding_agents.config import Settings, get_settings
from eu_funding_agents.db.session import get_db
from eu_funding_agents.services.catalog_freshness import CatalogFreshnessService
from eu_funding_agents.services.database_health import DatabaseHealthService
from eu_funding_agents.services.retrieval import MultilingualHybridRetriever

ROOT = Path(__file__).resolve().parents[2]

DbSession = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_database_health_service(
    session: DbSession,
    settings: AppSettings,
) -> DatabaseHealthService:
    return DatabaseHealthService(
        session,
        timeout_seconds=settings.database_health_timeout_seconds,
    )


def get_catalog_freshness_service(
    session: DbSession,
    settings: AppSettings,
) -> CatalogFreshnessService:
    return CatalogFreshnessService(session, max_age_hours=settings.call_refresh_hours)


@lru_cache
def get_recommendation_retriever() -> MultilingualHybridRetriever:
    from sentence_transformers import SentenceTransformer

    from eu_funding_agents.retrieval.dense import DEFAULT_MODEL, DEFAULT_MODEL_REVISION

    encoder = SentenceTransformer(DEFAULT_MODEL, revision=DEFAULT_MODEL_REVISION)
    return MultilingualHybridRetriever(
        encoder,
        cache_dir=ROOT / "data" / "processed" / "embeddings",
    )
