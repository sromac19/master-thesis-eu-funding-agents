from __future__ import annotations

import csv
import tempfile
import time
from pathlib import Path


def annotation_save_blockers(
    *, annotator: str, methodology_approved: bool, relevance: int | None
) -> tuple[str, ...]:
    blockers: list[str] = []
    if not annotator.strip():
        blockers.append("upiši pseudonim anotatora")
    if not methodology_approved:
        blockers.append("potvrdi odobrenu metodologiju")
    if relevance not in range(4):
        blockers.append("odaberi ocjenu 0–3")
    return tuple(blockers)


def upsert_csv_row(
    path: Path,
    *,
    fieldnames: list[str],
    key_fields: tuple[str, ...],
    row: dict[str, str],
) -> bool:
    if set(row) != set(fieldnames):
        raise ValueError("annotation row must contain exactly the configured fields")
    if any(not row[field].strip() for field in key_fields):
        raise ValueError("annotation key fields cannot be empty")

    existing: list[dict[str, str]] = []
    if path.exists():
        with path.open(encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames != fieldnames:
                raise ValueError("existing annotation CSV has unexpected columns")
            existing = list(reader)

    key = tuple(row[field] for field in key_fields)
    replaced = False
    updated: list[dict[str, str]] = []
    for item in existing:
        if tuple(item[field] for field in key_fields) == key:
            if not replaced:
                updated.append(row)
                replaced = True
            continue
        updated.append(item)
    if not replaced:
        updated.append(row)

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            delete=False,
            dir=path.parent,
            suffix=".tmp",
        ) as destination:
            temporary_path = Path(destination.name)
            writer = csv.DictWriter(destination, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(updated)
        for attempt in range(5):
            try:
                temporary_path.replace(path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.1 * (2**attempt))
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return replaced
