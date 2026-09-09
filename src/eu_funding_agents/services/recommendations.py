from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from eu_funding_agents.retrieval.corpus import load_active_call_corpus
from eu_funding_agents.retrieval.types import SearchDocument, SearchResult
from eu_funding_agents.schemas import (
    ProjectProfile,
    RecommendationItem,
    RecommendationPreviewResponse,
)
from eu_funding_agents.services.evidence import OfficialEvidenceService


class RecommendationPreviewService:
    def __init__(self, session: AsyncSession, retriever: RecommendationRetriever) -> None:
        self._session = session
        self._retriever = retriever

    async def preview(
        self, profile: ProjectProfile, *, top_k: int, as_of: date
    ) -> RecommendationPreviewResponse:
        corpus = await load_active_call_corpus(self._session, as_of=as_of)
        if not corpus:
            return RecommendationPreviewResponse(
                generated_at=datetime.now(UTC),
                as_of=as_of,
                method=self._retriever.method,
                recommendations=[],
                disclaimer="Decision support only; this is not legal advice.",
            )
        results = await asyncio.to_thread(
            self._retriever.search,
            corpus,
            profile.description,
            top_k=top_k,
        )
        evidence_by_call = await OfficialEvidenceService(self._session).search(
            source_call_ids=[result.call_id for result in results],
            query=profile.description,
        )
        documents_by_id = {document.call_id: document for document in corpus}
        return RecommendationPreviewResponse(
            generated_at=datetime.now(UTC),
            as_of=as_of,
            method=self._retriever.method,
            recommendations=[
                RecommendationItem(
                    call_id=result.call_id,
                    programme=result.programme,
                    title=result.title,
                    action_type=documents_by_id[result.call_id].action_type,
                    call_status=documents_by_id[result.call_id].status,
                    opening_date=documents_by_id[result.call_id].opening_date,
                    deadline=documents_by_id[result.call_id].deadline,
                    days_remaining=(documents_by_id[result.call_id].deadline - as_of).days,
                    budget_eur=documents_by_id[result.call_id].budget_eur,
                    funding_rate=documents_by_id[result.call_id].funding_rate,
                    applicant_conditions=documents_by_id[result.call_id].applicant_conditions,
                    consortium_conditions=documents_by_id[result.call_id].consortium_conditions,
                    trl_min=documents_by_id[result.call_id].trl_min,
                    trl_max=documents_by_id[result.call_id].trl_max,
                    fetched_at=documents_by_id[result.call_id].fetched_at,
                    relevance_score=result.score,
                    eligibility_status="REQUIRES_VERIFICATION",
                    official_url=result.official_url,
                    reasons_for=["The call covers topics that are similar to your project idea."],
                    reasons_against=[],
                    missing_information=[
                        "Confirm the applicant and partnership rules on the official call page."
                    ],
                    evidence=evidence_by_call.get(result.call_id, []),
                )
                for result in results
            ],
            disclaimer="Decision support only; this is not legal advice.",
        )


class RecommendationRetriever(Protocol):
    method: str

    def search(
        self,
        documents: list[SearchDocument],
        query: str,
        *,
        top_k: int,
    ) -> list[SearchResult]: ...
