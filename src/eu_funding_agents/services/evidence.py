from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from eu_funding_agents.db.models import CallDocument, CallDocumentChunk, FundingCall
from eu_funding_agents.retrieval.bm25 import tokenize
from eu_funding_agents.schemas import EvidenceCitation


class OfficialEvidenceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(
        self,
        *,
        source_call_ids: Sequence[str],
        query: str,
        limit_per_call: int = 2,
    ) -> dict[str, list[EvidenceCitation]]:
        call_ids = list(dict.fromkeys(source_call_ids))
        terms = list(dict.fromkeys(token for token in tokenize(query) if len(token) >= 3))[:12]
        if not call_ids or not terms:
            return {}

        ts_query = func.to_tsquery("simple", " | ".join(terms))
        score = func.ts_rank_cd(CallDocumentChunk.search_vector, ts_query)
        row_number = func.row_number().over(
            partition_by=FundingCall.source_call_id,
            order_by=(
                score.desc(),
                CallDocument.name,
                CallDocumentChunk.page.asc().nulls_last(),
                CallDocumentChunk.chunk_index,
            ),
        )
        latest_calls = (
            select(FundingCall.id)
            .where(FundingCall.source_call_id.in_(call_ids))
            .distinct(FundingCall.source, FundingCall.source_call_id)
            .order_by(
                FundingCall.source,
                FundingCall.source_call_id,
                FundingCall.fetched_at.desc(),
            )
        )
        ranked = (
            select(
                FundingCall.source_call_id.label("call_id"),
                CallDocument.name.label("document_name"),
                CallDocument.source_url,
                CallDocument.checksum.label("document_checksum"),
                CallDocumentChunk.page,
                CallDocumentChunk.section,
                CallDocumentChunk.content.label("excerpt"),
                CallDocumentChunk.content_checksum,
                row_number.label("position"),
            )
            .join(CallDocument, CallDocument.funding_call_id == FundingCall.id)
            .join(CallDocumentChunk, CallDocumentChunk.call_document_id == CallDocument.id)
            .where(
                FundingCall.id.in_(latest_calls),
                CallDocument.checksum_verified.is_(True),
                or_(
                    CallDocument.source_url.startswith("https://europa.eu/"),
                    CallDocument.source_url.like("https://%.europa.eu/%"),
                ),
                CallDocumentChunk.search_vector.op("@@")(ts_query),
            )
            .subquery()
        )
        rows = (
            await self._session.execute(
                select(ranked)
                .where(ranked.c.position <= limit_per_call)
                .order_by(ranked.c.call_id, ranked.c.position)
            )
        ).mappings()

        evidence: defaultdict[str, list[EvidenceCitation]] = defaultdict(list)
        for row in rows:
            evidence[row["call_id"]].append(
                EvidenceCitation(
                    document_name=row["document_name"],
                    source_url=row["source_url"],
                    page=row["page"],
                    section=row["section"],
                    excerpt=row["excerpt"],
                    document_checksum=row["document_checksum"],
                    content_checksum=row["content_checksum"],
                )
            )
        return dict(evidence)
