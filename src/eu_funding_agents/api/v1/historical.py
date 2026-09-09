from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from eu_funding_agents.db.session import get_db
from eu_funding_agents.schemas import HistoricalSimilarityRequest, HistoricalSimilarityResponse
from eu_funding_agents.services.historical_similarity import HistoricalSimilarityService

router = APIRouter(prefix="/api/v1/historical", tags=["historical"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]


@router.post(
    "/similar",
    response_model=HistoricalSimilarityResponse,
    status_code=200,
    summary="Find similar historical CORDIS projects",
    description=(
        "Returns explanatory historical project and participant-pattern signals without "
        "claiming formal eligibility or partner suitability."
    ),
)
async def similar_projects(
    request: HistoricalSimilarityRequest,
    session: DatabaseSession,
) -> HistoricalSimilarityResponse:
    return await HistoricalSimilarityService(session).search(
        request.project_description, top_k=request.top_k
    )
