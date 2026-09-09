from collections.abc import Awaitable, Callable
from time import perf_counter

import structlog
from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from eu_funding_agents.api.v1.health import router as health_router
from eu_funding_agents.api.v1.historical import router as historical_router
from eu_funding_agents.api.v1.recommendations import router as recommendations_router
from eu_funding_agents.metrics import HTTP_LATENCY, HTTP_REQUESTS
from eu_funding_agents.schemas import HealthResponse

logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    application = FastAPI(
        title="EU Funding Agents",
        version="0.1.0",
        description="Controlled multi-agent decision support for EU funding calls.",
    )

    @application.middleware("http")
    async def observe_request(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = getattr(request.scope.get("route"), "path", "__unmatched__")
            elapsed = perf_counter() - started
            HTTP_REQUESTS.labels(request.method, route, str(status_code)).inc()
            HTTP_LATENCY.labels(request.method, route).observe(elapsed)
            logger.info(
                "http_request_completed",
                method=request.method,
                route=route,
                status_code=status_code,
                duration_seconds=elapsed,
            )

    @application.get(
        "/health",
        response_model=HealthResponse,
        status_code=200,
        summary="Check API health",
        description="Checks whether the API process is running.",
    )
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @application.get(
        "/metrics",
        response_class=Response,
        status_code=200,
        summary="Expose Prometheus metrics",
        description="Returns process and EU Funding Agents HTTP metrics.",
        include_in_schema=False,
    )
    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    application.include_router(health_router)
    application.include_router(historical_router)
    application.include_router(recommendations_router)
    return application


app = create_app()
