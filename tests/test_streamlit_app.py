from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {
            "generated_at": "2026-09-06T12:00:00Z",
            "as_of": "2026-09-06",
            "method": "bm25",
            "recommendations": [
                {
                    "call_id": "HORIZON-TEST",
                    "programme": "Horizon Europe",
                    "title": "Verified test call",
                    "action_type": "RIA",
                    "call_status": "open",
                    "opening_date": "2026-06-01",
                    "deadline": "2027-01-01",
                    "days_remaining": 117,
                    "budget_eur": 12_000_000,
                    "funding_rate": 1.0,
                    "applicant_conditions": "Eligible legal entities.",
                    "consortium_conditions": "At least three partners.",
                    "trl_min": 4,
                    "trl_max": 6,
                    "fetched_at": "2026-09-06T12:00:00Z",
                    "relevance_score": 0.75,
                    "eligibility_status": "REQUIRES_VERIFICATION",
                    "official_url": "https://example.eu/call",
                    "reasons_for": ["Lexical match"],
                    "reasons_against": [],
                    "missing_information": ["Human verification"],
                    "evidence": [
                        {
                            "document_name": "Work Programme.pdf",
                            "source_url": "https://ec.europa.eu/work-programme.pdf",
                            "page": 12,
                            "section": "Eligibility",
                            "excerpt": "Official evidence excerpt.",
                            "document_checksum": "a" * 64,
                            "content_checksum": "b" * 64,
                        }
                    ],
                }
            ],
            "disclaimer": "Decision support only; this is not legal advice.",
        }


def test_streamlit_form_renders_recommendation(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(*args: object, **kwargs: object) -> FakeResponse:
        if args[0] == "http://127.0.0.1:8000/api/v1/historical/similar":
            return HistoricalFakeResponse()
        assert args[0] == "http://127.0.0.1:8000/api/v1/recommendations/preview"
        assert kwargs["json"]["profile"]["country"] == "HR"  # type: ignore[index]
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()

    app.text_area[0].set_value(
        "Projekt razvija digitalno rješenje za energetsku učinkovitost u industriji."
    )
    app.button[0].click().run()

    assert not app.exception
    assert len(app.expander) == 3
    assert app.expander[0].label == "Optional project details"
    assert app.expander[1].label == "🟢 1. Verified test call · 117 days left"
    assert app.expander[2].label == "Explore similar funded projects (optional)"
    assert [metric.label for metric in app.metric[:4]] == [
        "Matching calls",
        "Official links",
        "Source excerpts",
        "Need eligibility check",
    ]
    assert [metric.value for metric in app.metric[:4]] == ["1", "0", "1", "1"]
    assert [tab.label for tab in app.tabs] == [
        "Why this call",
        "Who can apply",
        "Official sources",
    ]
    markdown_values = [element.value for element in app.markdown]
    caption_values = [element.value for element in app.caption]
    assert any("🟢 Open now" in value and "🟠 Opening soon" in value for value in caption_values)
    assert any(
        "Application deadline" in value and "01 Jan 2027" in value for value in markdown_values
    )
    assert any("Total call budget" in value and "€12.0M" in value for value in markdown_values)
    assert not any("Match score" in value for value in markdown_values)
    assert not any("REQUIRES_VERIFICATION" in value for value in markdown_values)
    assert not any("Ciljani TRL" in value for value in markdown_values)
    assert app.get("link_button")[0].url == "https://example.eu/call"
    assert app.get("link_button")[1].url == "https://ec.europa.eu/work-programme.pdf"
    assert app.get("link_button")[2].url == "https://cordis.europa.eu/project/id/101"
    assert len(app.get("download_button")) == 1
    download = app.get("download_button")[0]
    assert download.label == "Download client report (PDF)"


class HistoricalFakeResponse(FakeResponse):
    def json(self) -> dict[str, Any]:
        return {
            "method": "postgresql_full_text_cordis",
            "similar_projects": [
                {
                    "project_id": "101",
                    "title": "Historical energy project",
                    "acronym": "ENERGY",
                    "framework_programme": "HORIZON",
                    "similarity_score": 0.5,
                    "official_url": "https://cordis.europa.eu/project/id/101",
                }
            ],
            "partner_signals": [
                {
                    "role": "coordinator",
                    "country": "DE",
                    "similar_project_count": 1,
                    "explanation": "Historical pattern only",
                }
            ],
            "limitation": "Historical signal only",
        }
