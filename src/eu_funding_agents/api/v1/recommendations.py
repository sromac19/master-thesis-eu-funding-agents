from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from eu_funding_agents.db.session import get_db
from eu_funding_agents.dependencies import get_recommendation_retriever
from eu_funding_agents.schemas import RecommendationPreviewRequest, RecommendationPreviewResponse
from eu_funding_agents.services.recommendations import (
    RecommendationPreviewService,
    RecommendationRetriever,
)

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
RecommendationRetrieverDependency = Annotated[
    RecommendationRetriever,
    Depends(get_recommendation_retriever),
]


@router.post(
    "/preview",
    response_model=RecommendationPreviewResponse,
    status_code=200,
    summary="Preview relevant active calls",
    description=(
        "Ranks confirmed active calls without persisting or sending the supplied profile to an LLM."
    ),
)
async def preview_recommendations(
    request: RecommendationPreviewRequest,
    session: DatabaseSession,
    retriever: RecommendationRetrieverDependency,
) -> RecommendationPreviewResponse:
    return await RecommendationPreviewService(session, retriever).preview(
        request.profile, top_k=request.top_k, as_of=request.as_of
    )
