from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterator
from io import TextIOWrapper
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

CORDIS_BULK_URL = "https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip"
CORDIS_REQUIRED_FILES = frozenset(
    {"project.csv", "organization.csv", "topics.csv", "euroSciVoc.csv"}
)
CORDIS_REQUIRED_HEADERS = {
    "project.csv": {"id", "status", "title", "frameworkProgramme", "objective"},
    "organization.csv": {"projectID", "organisationID", "name", "role", "country"},
    "topics.csv": {"projectID", "topic", "title"},
    "euroSciVoc.csv": {"projectID", "euroSciVocCode", "euroSciVocPath", "euroSciVocTitle"},
}


class CordisBulkError(ValueError):
    """Raised when a CORDIS bulk snapshot does not match its documented schema."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


class CordisBulkReader:
    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            with ZipFile(path) as archive:
                names = set(archive.namelist())
                missing = CORDIS_REQUIRED_FILES - names
                if missing:
                    raise CordisBulkError(
                        f"CORDIS ZIP is missing required files: {sorted(missing)}"
                    )
                for name, required in CORDIS_REQUIRED_HEADERS.items():
                    with archive.open(name) as raw:
                        text = TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                        headers = set(next(csv.reader(text, delimiter=";")))
                    if not required <= headers:
                        raise CordisBulkError(f"CORDIS {name} schema changed")
        except BadZipFile as exc:
            raise CordisBulkError("CORDIS bulk file is not a valid ZIP") from exc

    def rows(self, name: str) -> Iterator[dict[str, Any]]:
        if name not in CORDIS_REQUIRED_FILES:
            raise CordisBulkError(f"Unsupported CORDIS member: {name}")
        with ZipFile(self.path) as archive, archive.open(name) as raw:
            text = TextIOWrapper(raw, encoding="utf-8-sig", newline="")
            yield from csv.DictReader(text, delimiter=";")
