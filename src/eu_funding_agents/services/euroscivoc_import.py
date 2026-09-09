from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from eu_funding_agents.db.models import (
    DatasetSnapshot,
    EuroSciVocBroaderRelation,
    EuroSciVocConcept,
)
from eu_funding_agents.ingestion.euroscivoc import (
    EUROSCIVOC_TTL_URL,
    file_sha256,
    parse_euroscivoc,
)


@dataclass(frozen=True)
class EuroSciVocImportReport:
    snapshot_id: uuid.UUID
    checksum: str
    concepts: int
    broader_relations: int
    reused_snapshot: bool


async def import_euroscivoc(
    session: AsyncSession,
    *,
    path: Path,
    fetched_at: datetime,
    source_url: str = EUROSCIVOC_TTL_URL,
) -> EuroSciVocImportReport:
    checksum = file_sha256(path)
    existing = await session.scalar(
        select(DatasetSnapshot).where(
            DatasetSnapshot.source == "euroscivoc",
            DatasetSnapshot.checksum == checksum,
        )
    )
    if existing is not None:
        return EuroSciVocImportReport(
            snapshot_id=existing.id,
            checksum=checksum,
            concepts=existing.row_counts.get("concepts", 0),
            broader_relations=existing.row_counts.get("broader_relations", 0),
            reused_snapshot=True,
        )

    records = parse_euroscivoc(path)
    snapshot_id = uuid.uuid4()
    concept_ids = {record.uri: uuid.uuid4() for record in records}
    await session.execute(
        insert(DatasetSnapshot),
        [
            {
                "id": snapshot_id,
                "source": "euroscivoc",
                "source_url": source_url,
                "checksum": checksum,
                "fetched_at": fetched_at,
                "local_path": str(path),
                "row_counts": {},
            }
        ],
    )
    await session.execute(
        insert(EuroSciVocConcept),
        [
            {
                "id": concept_ids[record.uri],
                "snapshot_id": snapshot_id,
                "uri": record.uri,
                "notation": record.notation,
                "version": record.version,
                "deprecated": record.deprecated,
                "preferred_labels": record.preferred_labels,
                "alternative_labels": record.alternative_labels,
            }
            for record in records
        ],
    )
    relations = [
        {
            "id": uuid.uuid4(),
            "concept_id": concept_ids[record.uri],
            "broader_concept_id": concept_ids[parent_uri],
        }
        for record in records
        for parent_uri in record.broader_uris
    ]
    if relations:
        await session.execute(insert(EuroSciVocBroaderRelation), relations)
    counts = {"concepts": len(records), "broader_relations": len(relations)}
    await session.execute(
        DatasetSnapshot.__table__.update()
        .where(DatasetSnapshot.id == snapshot_id)
        .values(row_counts=counts)
    )
    await session.commit()
    return EuroSciVocImportReport(
        snapshot_id=snapshot_id,
        checksum=checksum,
        concepts=len(records),
        broader_relations=len(relations),
        reused_snapshot=False,
    )
