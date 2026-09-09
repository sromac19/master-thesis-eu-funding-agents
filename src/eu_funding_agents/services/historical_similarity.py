from __future__ import annotations

import re

from sqlalchemy import desc, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eu_funding_agents.db.models import DatasetSnapshot, HistoricalProject, Participant
from eu_funding_agents.schemas import (
    HistoricalSimilarityResponse,
    PartnerSignalItem,
    SimilarProjectItem,
)


class HistoricalSimilarityService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(self, project_description: str, *, top_k: int) -> HistoricalSimilarityResponse:
        latest_snapshot = (
            select(DatasetSnapshot.id)
            .where(DatasetSnapshot.source == "cordis_horizon")
            .order_by(DatasetSnapshot.fetched_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        tokens = list(dict.fromkeys(re.findall(r"\w{2,}", project_description.lower())))[:30]
        query = func.to_tsquery("simple", " | ".join(tokens or ["no_search_tokens"]))
        rank = func.ts_rank_cd(HistoricalProject.search_vector, query).label("similarity_score")
        statement = (
            select(HistoricalProject, rank)
            .where(
                HistoricalProject.snapshot_id == latest_snapshot,
                HistoricalProject.search_vector.op("@@")(query),
            )
            .order_by(desc(rank), HistoricalProject.source_project_id)
            .limit(top_k)
        )
        rows = list((await self._session.execute(statement)).all())
        projects = [
            SimilarProjectItem(
                project_id=project.source_project_id,
                title=project.title,
                acronym=project.acronym,
                framework_programme=project.framework_programme,
                similarity_score=float(score),
                official_url=f"https://cordis.europa.eu/project/id/{project.source_project_id}",
            )
            for project, score in rows
        ]

        partner_signals: list[PartnerSignalItem] = []
        project_ids = [project.id for project, _ in rows]
        if project_ids:
            count = func.count(distinct(Participant.project_id)).label("project_count")
            partner_statement = (
                select(Participant.role, Participant.country, count)
                .where(Participant.project_id.in_(project_ids))
                .group_by(Participant.role, Participant.country)
                .order_by(desc(count), Participant.role, Participant.country)
                .limit(8)
            )
            partner_rows = (await self._session.execute(partner_statement)).all()
            partner_signals = [
                PartnerSignalItem(
                    role=role,
                    country=country,
                    similar_project_count=int(project_count),
                    explanation=(
                        "Observed participant role and country in the returned historical "
                        "CORDIS projects; not a formal call requirement or partner endorsement."
                    ),
                )
                for role, country, project_count in partner_rows
            ]
        return HistoricalSimilarityResponse(
            method="postgresql_full_text_cordis",
            similar_projects=projects,
            partner_signals=partner_signals,
            limitation=(
                "Historical similarity and participant patterns are explanatory signals only; "
                "they do not prove eligibility or partner suitability."
            ),
        )
