from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eu_funding_agents.db.models import FundingCall, FundingCallStatus
from eu_funding_agents.retrieval.types import SearchDocument


async def load_active_call_corpus(session: AsyncSession, *, as_of: date) -> list[SearchDocument]:
    rows = (
        await session.scalars(
            select(FundingCall)
            .where(
                FundingCall.status.in_([FundingCallStatus.OPEN, FundingCallStatus.FORTHCOMING]),
                FundingCall.deadline.is_not(None),
                FundingCall.deadline >= as_of,
            )
            .order_by(FundingCall.fetched_at.desc())
        )
    ).all()
    latest: dict[tuple[str, str], FundingCall] = {}
    for call in rows:
        latest.setdefault((call.source, call.source_call_id), call)
    return [
        SearchDocument(
            call_id=call.source_call_id,
            title=call.title,
            text="\n".join(
                part
                for part in (
                    call.title,
                    call.description,
                    call.scope,
                    call.expected_outcomes,
                    call.expected_impact,
                )
                if part
            ),
            programme=call.programme,
            official_url=call.official_url,
            status=call.status.value,
            opening_date=call.opening_date,
            deadline=call.deadline,
            budget_eur=float(call.budget_eur) if call.budget_eur is not None else None,
            funding_rate=float(call.funding_rate) if call.funding_rate is not None else None,
            action_type=call.action_type,
            applicant_conditions=call.applicant_conditions,
            consortium_conditions=call.consortium_conditions,
            trl_min=call.trl_min,
            trl_max=call.trl_max,
            fetched_at=call.fetched_at,
        )
        for call in sorted(latest.values(), key=lambda item: item.source_call_id)
    ]
