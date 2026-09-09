"""Load the small public demo catalogue without contacting external services."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from eu_funding_agents.db.models import FundingCall, FundingCallStatus
from eu_funding_agents.db.session import async_session_factory

ROOT = Path(__file__).resolve().parents[1]
DEMO_PATH = ROOT / "data" / "demo" / "funding_calls.json"
FETCHED_AT = datetime.fromisoformat("2026-09-06T00:43:22+00:00")


def load_records(path: Path = DEMO_PATH) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list):
        raise TypeError("Demo catalogue has no records list")
    normalized: list[dict[str, object]] = []
    for raw in records:
        if not isinstance(raw, dict):
            raise TypeError("Demo catalogue contains an invalid record")
        normalized.append(
            {
                "source_call_id": str(raw["source_call_id"]),
                "topic_id": str(raw["source_call_id"]),
                "programme": str(raw["programme"]),
                "title": str(raw["title"]),
                "description": str(raw["description"]),
                "scope": "",
                "expected_outcomes": "",
                "expected_impact": "",
                "action_type": None,
                "status": FundingCallStatus(str(raw["status"])),
                "opening_date": datetime.fromisoformat(str(raw["opening_date"])).date(),
                "deadline": datetime.fromisoformat(str(raw["deadline"])).date(),
                "budget_eur": Decimal(str(raw["budget_eur"])),
                "funding_rate": None,
                "applicant_conditions": "",
                "consortium_conditions": "",
                "trl_min": None,
                "trl_max": None,
                "official_url": str(raw["official_url"]),
                "source": "demo_sedia",
                "fetched_at": FETCHED_AT,
                "adapter_version": "demo-20260906",
                "snapshot_checksum": "demo-derived-from-20260906",
                "document_checksum": None,
            }
        )
    return normalized


async def import_records(records: list[dict[str, object]]) -> tuple[int, int]:
    async with async_session_factory() as session:
        existing = set(
            (
                await session.scalars(
                    select(FundingCall.source_call_id).where(FundingCall.source == "demo_sedia")
                )
            ).all()
        )
        pending = [record for record in records if record["source_call_id"] not in existing]
        session.add_all(FundingCall(**record) for record in pending)
        await session.commit()
    return len(pending), len(records) - len(pending)


def main() -> None:
    records = load_records()
    inserted, skipped = asyncio.run(import_records(records))
    print(f"Demo catalogue: inserted={inserted}, already_present={skipped}")


if __name__ == "__main__":
    main()
