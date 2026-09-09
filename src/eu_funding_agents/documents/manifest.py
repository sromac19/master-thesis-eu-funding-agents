from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


class DocumentManifestError(ValueError):
    pass


@dataclass(frozen=True)
class ManifestDocument:
    title: str
    source_url: str
    media_type: str
    checksum: str
    path: Path
    topic_ids: tuple[str, ...]
    fetched_at: datetime


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_sedia_document_manifest(path: Path, *, root: Path) -> list[ManifestDocument]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(payload["fetched_at"])
        raw_documents = payload["downloaded_documents"]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DocumentManifestError("Document manifest has an invalid structure") from exc
    if payload.get("source") != "eu_funding_tenders_portal" or not isinstance(raw_documents, list):
        raise DocumentManifestError("Document manifest has an invalid source or document list")
    if fetched_at.tzinfo is None:
        raise DocumentManifestError("Document manifest fetched_at must include a timezone")

    allowed_directory = (root / "data" / "raw" / "documents").resolve()
    documents: list[ManifestDocument] = []
    for index, raw in enumerate(raw_documents, start=1):
        try:
            if not isinstance(raw, dict) or not isinstance(raw["topic_ids"], list):
                raise TypeError
            document_path = (root / str(raw["path"])).resolve()
            title = str(raw["title"]).strip()
            source_url = str(raw["source_url"]).strip()
            media_type = str(raw["media_type"]).casefold()
            checksum = str(raw["checksum"]).upper()
            topic_ids = tuple(dict.fromkeys(str(item).strip() for item in raw["topic_ids"]))
        except (KeyError, TypeError) as exc:
            raise DocumentManifestError(f"Manifest document {index} is invalid") from exc
        parsed_url = urlparse(source_url)
        hostname = (parsed_url.hostname or "").casefold()
        if not title or not all(topic_ids):
            raise DocumentManifestError(f"Manifest document {index} has empty metadata")
        if parsed_url.scheme != "https" or not (
            hostname == "europa.eu" or hostname.endswith(".europa.eu")
        ):
            raise DocumentManifestError(f"Manifest document {index} URL is not official")
        if media_type != "application/pdf" or document_path.suffix.casefold() != ".pdf":
            raise DocumentManifestError(f"Manifest document {index} is not a PDF")
        if not document_path.is_relative_to(allowed_directory) or not document_path.is_file():
            raise DocumentManifestError(f"Manifest document {index} path is not allowed")
        if len(checksum) != 64 or _sha256(document_path) != checksum:
            raise DocumentManifestError(f"Manifest document {index} checksum does not match")
        documents.append(
            ManifestDocument(
                title=title,
                source_url=source_url,
                media_type=media_type,
                checksum=checksum,
                path=document_path,
                topic_ids=topic_ids,
                fetched_at=fetched_at,
            )
        )
    return documents
