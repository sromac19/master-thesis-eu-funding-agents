from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from eu_funding_agents.db.models import (
    DatasetSnapshot,
    HistoricalProject,
    HistoricalProjectEuroSciVoc,
    HistoricalProjectTopic,
    Participant,
)
from eu_funding_agents.ingestion.cordis import CORDIS_BULK_URL, CordisBulkReader, file_sha256


@dataclass(frozen=True)
class CordisImportReport:
    snapshot_id: uuid.UUID
    checksum: str
    projects: int
    participants: int
    topics: int
    classifications: int
    skipped_orphans: int
    reused_snapshot: bool


def _optional(value: str | None) -> str | None:
    stripped = value.strip() if value else ""
    return stripped or None


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation:
        return None


def _boolean(value: str | None) -> bool | None:
    if not value:
        return None
    normalized = value.casefold()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    return None


async def _insert_batches(
    session: AsyncSession,
    model: type[Any],
    rows: Iterable[dict[str, Any]],
    *,
    batch_size: int = 1000,
) -> int:
    batch: list[dict[str, Any]] = []
    count = 0
    for row in rows:
        batch.append(row)
        if len(batch) == batch_size:
            await session.execute(insert(model), batch)
            count += len(batch)
            batch.clear()
    if batch:
        await session.execute(insert(model), batch)
        count += len(batch)
    return count


async def import_cordis_bulk(
    session: AsyncSession,
    *,
    path: Path,
    fetched_at: datetime,
    source_url: str = CORDIS_BULK_URL,
) -> CordisImportReport:
    reader = CordisBulkReader(path)
    checksum = file_sha256(path)
    existing = await session.scalar(
        select(DatasetSnapshot).where(
            DatasetSnapshot.source == "cordis_horizon",
            DatasetSnapshot.checksum == checksum,
        )
    )
    if existing is not None:
        counts = existing.row_counts
        return CordisImportReport(
            snapshot_id=existing.id,
            checksum=checksum,
            projects=counts.get("projects", 0),
            participants=counts.get("participants", 0),
            topics=counts.get("topics", 0),
            classifications=counts.get("classifications", 0),
            skipped_orphans=counts.get("skipped_orphans", 0),
            reused_snapshot=True,
        )

    snapshot_id = uuid.uuid4()
    await session.execute(
        insert(DatasetSnapshot),
        [
            {
                "id": snapshot_id,
                "source": "cordis_horizon",
                "source_url": source_url,
                "checksum": checksum,
                "fetched_at": fetched_at,
                "local_path": str(path),
                "row_counts": {},
            }
        ],
    )
    project_ids: dict[str, uuid.UUID] = {}

    def project_rows() -> Iterable[dict[str, Any]]:
        for row in reader.rows("project.csv"):
            source_id = row["id"]
            project_id = uuid.uuid4()
            project_ids[source_id] = project_id
            yield {
                "id": project_id,
                "snapshot_id": snapshot_id,
                "source_project_id": source_id,
                "acronym": _optional(row.get("acronym")),
                "status": row["status"] or "UNKNOWN",
                "title": row["title"],
                "objective": row.get("objective", ""),
                "framework_programme": row["frameworkProgramme"],
                "funding_scheme": _optional(row.get("fundingScheme")),
                "start_date": _date(row.get("startDate")),
                "end_date": _date(row.get("endDate")),
                "total_cost": _decimal(row.get("totalCost")),
                "eu_contribution": _decimal(row.get("ecMaxContribution")),
            }

    projects = await _insert_batches(session, HistoricalProject, project_rows())
    skipped_orphans = 0

    def related_rows(name: str, builder: Any) -> Iterable[dict[str, Any]]:
        nonlocal skipped_orphans
        seen: set[tuple[Any, ...]] = set()
        for row in reader.rows(name):
            project_id = project_ids.get(row["projectID"])
            if project_id is None:
                skipped_orphans += 1
                continue
            built, identity = builder(project_id, row)
            if identity in seen:
                continue
            seen.add(identity)
            yield built

    participants = await _insert_batches(
        session,
        Participant,
        related_rows(
            "organization.csv",
            lambda project_id, row: (
                {
                    "id": uuid.uuid4(),
                    "project_id": project_id,
                    "source_organisation_id": row["organisationID"],
                    "name": row["name"],
                    "country": _optional(row.get("country")),
                    "role": row.get("role") or "participant",
                    "sme": _boolean(row.get("SME")),
                    "eu_contribution": _decimal(row.get("ecContribution")),
                },
                (project_id, row["organisationID"], row.get("role") or "participant"),
            ),
        ),
    )
    topics = await _insert_batches(
        session,
        HistoricalProjectTopic,
        related_rows(
            "topics.csv",
            lambda project_id, row: (
                {
                    "id": uuid.uuid4(),
                    "project_id": project_id,
                    "topic_id": row["topic"],
                    "title": _optional(row.get("title")),
                },
                (project_id, row["topic"]),
            ),
        ),
    )
    classifications = await _insert_batches(
        session,
        HistoricalProjectEuroSciVoc,
        related_rows(
            "euroSciVoc.csv",
            lambda project_id, row: (
                {
                    "id": uuid.uuid4(),
                    "project_id": project_id,
                    "code": row["euroSciVocCode"],
                    "path": row["euroSciVocPath"],
                    "title": row["euroSciVocTitle"],
                    "description": _optional(row.get("euroSciVocDescription")),
                },
                (project_id, row["euroSciVocCode"]),
            ),
        ),
    )
    counts = {
        "projects": projects,
        "participants": participants,
        "topics": topics,
        "classifications": classifications,
        "skipped_orphans": skipped_orphans,
    }
    await session.execute(
        DatasetSnapshot.__table__.update()
        .where(DatasetSnapshot.id == snapshot_id)
        .values(row_counts=counts)
    )
    await session.commit()
    return CordisImportReport(
        snapshot_id,
        checksum,
        projects,
        participants,
        topics,
        classifications,
        skipped_orphans,
        False,
    )
