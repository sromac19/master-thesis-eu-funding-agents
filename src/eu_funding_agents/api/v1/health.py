from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from eu_funding_agents.dependencies import (
    get_catalog_freshness_service,
    get_database_health_service,
)
from eu_funding_agents.schemas import CatalogFreshnessResponse, DatabaseHealthResponse
from eu_funding_agents.services.catalog_freshness import (
    CatalogFreshnessService,
    CatalogStaleError,
)
from eu_funding_agents.services.database_health import (
    DatabaseHealthService,
    DatabaseUnavailableError,
)

router = APIRouter(tags=["health"])
DatabaseHealth = Annotated[DatabaseHealthService, Depends(get_database_health_service)]
CatalogHealth = Annotated[CatalogFreshnessService, Depends(get_catalog_freshness_service)]


@router.get(
    "/health/db",
    response_model=DatabaseHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Check database health",
    description="Actively verifies that the API can execute a query against PostgreSQL.",
)
async def database_health(service: DatabaseHealth) -> DatabaseHealthResponse:
    try:
        await service.check()
    except DatabaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from exc
    return DatabaseHealthResponse(status="ok", database="reachable")


@router.get(
    "/health/catalog",
    response_model=CatalogFreshnessResponse,
    status_code=status.HTTP_200_OK,
    summary="Check funding catalog freshness",
    description="Returns 503 when the catalog is empty or older than CALL_REFRESH_HOURS.",
)
async def catalog_health(service: CatalogHealth) -> CatalogFreshnessResponse:
    try:
        freshness = await service.check()
    except CatalogStaleError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Funding catalog is unavailable or stale",
        ) from exc
    return CatalogFreshnessResponse(
        status="ok",
        last_fetched_at=freshness.last_fetched_at,
        age_hours=freshness.age_hours,
        max_age_hours=freshness.max_age_hours,
        needs_refresh=False,
    )
