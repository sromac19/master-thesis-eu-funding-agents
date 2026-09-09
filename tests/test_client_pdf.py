from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from eu_funding_agents.reporting import build_client_pdf


def _report() -> dict[str, object]:
    return {
        "as_of": "2026-09-07",
        "recommendations": [
            {
                "call_id": "HORIZON-TEST-01",
                "programme": "Horizon Europe",
                "title": "Clean energy solutions for European industry",
                "deadline": "2027-01-15",
                "days_remaining": 130,
                "call_status": "open",
                "budget_eur": 12_000_000,
                "funding_rate": 1.0,
                "official_url": "https://ec.europa.eu/example-call",
                "reasons_for": [
                    "Multilingual lexical and semantic match with the project description"
                ],
            }
        ],
    }


def test_client_pdf_contains_readable_report_and_link() -> None:
    profile = {
        "description": (
            "Hrvatski startup razvija rješenje za smanjenje potrošnje energije i traži "
            "europske partnere."
        ),
        "country": "HR",
        "organisation_type": "Startup",
        "sectors": ["Energy and environment"],
        "requested_budget_eur": 700_000,
    }

    payload = build_client_pdf(profile, _report())

    assert payload.startswith(b"%PDF-")
    reader = PdfReader(BytesIO(payload))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "EU Funding Opportunity Report" in text
    assert "potrošnje energije" in text
    assert "traži europske partnere" in text
    assert "Clean energy solutions for European industry" in text
    assert "Eligibility check required" in text
    assert "Recommended next step" in text
    annotations = [
        annotation.get_object()
        for page in reader.pages
        for annotation in (page.get("/Annots") or [])
    ]
    assert any(
        annotation.get("/A", {}).get("/URI") == "https://ec.europa.eu/example-call"
        for annotation in annotations
    )


def test_client_pdf_limits_number_of_calls() -> None:
    report = _report()
    original = report["recommendations"][0]  # type: ignore[index]
    report["recommendations"] = [
        {**original, "title": f"Call {index}", "call_id": f"CALL-{index}"}  # type: ignore[misc]
        for index in range(1, 8)
    ]

    payload = build_client_pdf(
        {"description": "A sufficiently detailed project description for the client report."},
        report,
        max_calls=5,
    )
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(payload)).pages)

    assert "Call 5" in text
    assert "Call 6" not in text


def test_client_pdf_rejects_empty_call_limit() -> None:
    try:
        build_client_pdf({}, _report(), max_calls=0)
    except ValueError as exc:
        assert str(exc) == "max_calls must be at least 1"
    else:
        raise AssertionError("Expected max_calls validation to fail")
