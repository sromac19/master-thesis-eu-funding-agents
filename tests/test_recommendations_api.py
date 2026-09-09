from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import cast

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from eu_funding_agents.db.models import FundingCall, FundingCallStatus
from eu_funding_agents.db.session import get_db
from eu_funding_agents.dependencies import get_recommendation_retriever
from eu_funding_agents.main import app
from eu_funding_agents.retrieval.types import SearchDocument, SearchResult


class FakeScalarResult:
    def __init__(self, rows: list[FundingCall]) -> None:
        self._rows = rows

    def all(self) -> list[FundingCall]:
        return self._rows


class FakeEvidenceResult:
    def mappings(self) -> list[dict[str, object]]:
        return [
            {
                "call_id": "HORIZON-FARM",
                "document_name": "Work Programme.pdf",
                "source_url": "https://ec.europa.eu/work-programme.pdf",
                "document_checksum": "A" * 64,
                "page": 12,
                "section": "Eligibility",
                "excerpt": "Applicants may develop sensors for sustainable agriculture.",
                "content_checksum": "b" * 64,
                "position": 1,
            }
        ]


class FakeSession:
    async def scalars(self, statement: object) -> FakeScalarResult:
        assert statement is not None
        return FakeScalarResult(
            [
                FundingCall(
                    source_call_id="HORIZON-FARM",
                    programme="Horizon Europe",
                    title="Digital agriculture",
                    description="Sensors for irrigation and sustainable food production",
                    action_type="RIA",
                    status=FundingCallStatus.OPEN,
                    opening_date=date(2026, 6, 1),
                    deadline=date(2027, 1, 1),
                    budget_eur=12_000_000,
                    funding_rate=1,
                    applicant_conditions="Applicants must be established in an eligible country.",
                    consortium_conditions="At least three independent entities.",
                    trl_min=4,
                    trl_max=6,
                    official_url="https://ec.europa.eu/farm",
                    source="sedia",
                    fetched_at=datetime(2026, 9, 6, tzinfo=UTC),
                )
            ]
        )

    async def execute(self, statement: object) -> FakeEvidenceResult:
        assert statement is not None
        return FakeEvidenceResult()


async def fake_db() -> AsyncIterator[AsyncSession]:
    yield cast(AsyncSession, FakeSession())


class FakeMultilingualRetriever:
    method = "hybrid_multilingual"

    def search(
        self,
        documents: list[SearchDocument],
        query: str,
        *,
        top_k: int,
    ) -> list[SearchResult]:
        assert "navodnjavanje" in query
        assert len(documents) == 1
        document = documents[0]
        return [
            SearchResult(
                call_id=document.call_id,
                title=document.title,
                programme=document.programme,
                official_url=document.official_url,
                score=0.75,
                components={"bm25": 1.0, "dense": 1.0},
            )
        ][:top_k]


def fake_retriever() -> FakeMultilingualRetriever:
    return FakeMultilingualRetriever()


def teardown_function() -> None:
    app.dependency_overrides.clear()


def _payload() -> dict[str, object]:
    return {
        "profile": {
            "description": "Senzori za pametno navodnjavanje i održivu proizvodnju hrane",
            "country": "HR",
            "organisation_type": "SME",
        },
        "top_k": 5,
        "as_of": "2026-09-06",
    }


def test_preview_returns_separate_relevance_and_unverified_eligibility() -> None:
    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_recommendation_retriever] = fake_retriever

    response = TestClient(app).post("/api/v1/recommendations/preview", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["method"] == "hybrid_multilingual"
    assert body["recommendations"][0]["call_id"] == "HORIZON-FARM"
    assert body["recommendations"][0]["eligibility_status"] == "REQUIRES_VERIFICATION"
    assert body["recommendations"][0]["official_url"] == "https://ec.europa.eu/farm"
    assert body["recommendations"][0]["call_status"] == "open"
    assert body["recommendations"][0]["deadline"] == "2027-01-01"
    assert body["recommendations"][0]["days_remaining"] == 117
    assert body["recommendations"][0]["budget_eur"] == 12_000_000
    assert body["recommendations"][0]["funding_rate"] == 1
    assert body["recommendations"][0]["trl_min"] == 4
    assert body["recommendations"][0]["trl_max"] == 6
    assert body["recommendations"][0]["evidence"][0]["page"] == 12
    assert body["recommendations"][0]["evidence"][0]["source_url"] == (
        "https://ec.europa.eu/work-programme.pdf"
    )
    assert "not legal advice" in body["disclaimer"]


def test_preview_rejects_short_project_description() -> None:
    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_recommendation_retriever] = fake_retriever
    payload = _payload()
    payload["profile"] = {
        "description": "too short",
        "country": "HR",
        "organisation_type": "SME",
    }

    response = TestClient(app).post("/api/v1/recommendations/preview", json=payload)

    assert response.status_code == 422
