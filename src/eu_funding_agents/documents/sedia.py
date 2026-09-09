from __future__ import annotations

import hashlib
import os
import re
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Self
from urllib.parse import unquote, urlparse

import httpx

SEDIA_DOCUMENT_MAX_BYTES = 5 * 1024 * 1024
SEDIA_DOCUMENT_MEDIA_TYPES = frozenset({"text/plain"})
SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}")
OFFICIAL_DOCUMENT_SUFFIXES = frozenset({".pdf", ".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".zip"})
OFFICIAL_DOCUMENT_METADATA_FIELDS = ("topicConditions", "supportInfo", "sepTemplate")


class SediaDocumentError(ValueError):
    """Raised when embedded SEDIA document content cannot be verified."""


@dataclass(frozen=True)
class OfficialDocumentLink:
    title: str
    url: str


@dataclass(frozen=True)
class DownloadedDocument:
    title: str
    source_url: str
    media_type: str
    checksum: str
    byte_size: int
    path: Path


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[OfficialDocumentLink] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        self._href = dict(attrs).get("href")
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "a" and self._href is not None:
            title = " ".join("".join(self._text).split()) or Path(urlparse(self._href).path).name
            self.links.append(OfficialDocumentLink(title=title, url=self._href))
            self._href = None
            self._text = []


def _is_official_download_url(url: str) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").casefold()
    suffix = Path(unquote(parsed.path)).suffix.casefold()
    return (
        parsed.scheme == "https"
        and (hostname == "europa.eu" or hostname.endswith(".europa.eu"))
        and suffix in OFFICIAL_DOCUMENT_SUFFIXES
    )


def extract_official_document_links(record: dict[str, Any]) -> list[OfficialDocumentLink]:
    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        raise SediaDocumentError("SEDIA document metadata is missing")

    unique: dict[str, OfficialDocumentLink] = {}
    for field in OFFICIAL_DOCUMENT_METADATA_FIELDS:
        raw_values = metadata.get(field, [])
        values = raw_values if isinstance(raw_values, list) else [raw_values]
        for value in values:
            if not isinstance(value, str):
                continue
            parser = _AnchorParser()
            parser.feed(value)
            for link in parser.links:
                if _is_official_download_url(link.url):
                    unique.setdefault(link.url, link)
    return list(unique.values())


class OfficialDocumentDownloader:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 30.0,
        max_bytes: int = 25 * 1024 * 1024,
        max_retries: int = 2,
        backoff_seconds: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout_seconds <= 0 or max_bytes <= 0 or max_retries < 0 or backoff_seconds < 0:
            raise ValueError("Document download limits must be positive")
        self._client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=True)
        self._owns_client = client is None
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        if self._owns_client:
            self._client.close()

    def download(self, link: OfficialDocumentLink, *, directory: Path) -> DownloadedDocument:
        if not _is_official_download_url(link.url):
            raise SediaDocumentError("Document URL is not an allowed official EU download")
        directory.mkdir(parents=True, exist_ok=True)

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return self._download_once(link, directory=directory)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                retryable_status = isinstance(exc, httpx.HTTPStatusError) and (
                    exc.response.status_code == 429 or exc.response.status_code >= 500
                )
                if isinstance(exc, httpx.HTTPStatusError) and not retryable_status:
                    break
                if attempt == self._max_retries:
                    break
                self._sleep(self._backoff_seconds * (2**attempt))
        raise SediaDocumentError("Official document download failed") from last_error

    def _download_once(
        self,
        link: OfficialDocumentLink,
        *,
        directory: Path,
    ) -> DownloadedDocument:
        suffix = Path(unquote(urlparse(link.url).path)).suffix.casefold()
        temporary_path: Path | None = None
        try:
            with self._client.stream("GET", link.url, timeout=self._timeout_seconds) as response:
                response.raise_for_status()
                declared_size = response.headers.get("content-length")
                if declared_size is not None and int(declared_size) > self._max_bytes:
                    raise SediaDocumentError("Official document exceeds the size limit")
                media_type = response.headers.get("content-type", "").split(";", 1)[0].casefold()
                hasher = hashlib.sha256()
                byte_size = 0
                header = b""
                with tempfile.NamedTemporaryFile(delete=False, dir=directory) as temporary_file:
                    temporary_path = Path(temporary_file.name)
                    for chunk in response.iter_bytes():
                        byte_size += len(chunk)
                        if byte_size > self._max_bytes:
                            raise SediaDocumentError("Official document exceeds the size limit")
                        if len(header) < 8:
                            header += chunk[: 8 - len(header)]
                        hasher.update(chunk)
                        temporary_file.write(chunk)

            self._validate_magic_bytes(suffix=suffix, header=header)
            self._validate_media_type(suffix=suffix, media_type=media_type)
            checksum = hasher.hexdigest().upper()
            destination = directory / f"{checksum}{suffix}"
            if destination.exists():
                temporary_path.unlink()
            else:
                os.replace(temporary_path, destination)
            temporary_path = None
            return DownloadedDocument(
                title=link.title,
                source_url=link.url,
                media_type=media_type,
                checksum=checksum,
                byte_size=byte_size,
                path=destination,
            )
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError):
            raise
        except SediaDocumentError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise SediaDocumentError("Official document response is invalid") from exc
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    @staticmethod
    def _validate_magic_bytes(*, suffix: str, header: bytes) -> None:
        if suffix == ".pdf" and not header.startswith(b"%PDF-"):
            raise SediaDocumentError("Downloaded PDF has invalid magic bytes")
        if suffix in {".docx", ".xlsx", ".xlsm", ".zip"} and not header.startswith(b"PK\x03\x04"):
            raise SediaDocumentError("Downloaded archive document has invalid magic bytes")
        if suffix in {".doc", ".xls"} and not header.startswith(b"\xd0\xcf\x11\xe0"):
            raise SediaDocumentError("Downloaded Office document has invalid magic bytes")

    @staticmethod
    def _validate_media_type(*, suffix: str, media_type: str) -> None:
        allowed_by_suffix = {
            ".pdf": {"application/pdf", "application/octet-stream"},
            ".doc": {"application/msword", "application/octet-stream"},
            ".docx": {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/octet-stream",
            },
            ".xls": {"application/vnd.ms-excel", "application/octet-stream"},
            ".xlsx": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/octet-stream",
            },
            ".xlsm": {"application/vnd.ms-excel.sheet.macroenabled.12", "application/octet-stream"},
            ".zip": {"application/zip", "application/octet-stream"},
        }
        if media_type not in allowed_by_suffix[suffix]:
            raise SediaDocumentError("Downloaded document has an invalid content type")


def _first_metadata_value(metadata: dict[str, Any], key: str) -> Any:
    value = metadata.get(key)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def extract_sedia_document(
    record: dict[str, Any],
    *,
    fetched_at: datetime,
    max_bytes: int = SEDIA_DOCUMENT_MAX_BYTES,
) -> dict[str, Any]:
    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        raise SediaDocumentError("SEDIA document metadata is missing")

    content = record.get("content")
    if not isinstance(content, str) or not content:
        raise SediaDocumentError("SEDIA document content is missing")
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > max_bytes:
        raise SediaDocumentError("SEDIA document exceeds the configured size limit")

    media_type = _first_metadata_value(metadata, "es_ContentType")
    if media_type not in SEDIA_DOCUMENT_MEDIA_TYPES:
        raise SediaDocumentError("SEDIA document has an unsupported media type")

    checksum = record.get("checksum") or _first_metadata_value(metadata, "esST_checksum")
    if not isinstance(checksum, str) or SHA256_PATTERN.fullmatch(checksum) is None:
        raise SediaDocumentError("SEDIA document has no valid SHA-256 checksum")
    actual_checksum = hashlib.sha256(content_bytes).hexdigest().upper()
    checksum_verified = actual_checksum.casefold() == checksum.casefold()

    source_url = _first_metadata_value(metadata, "esST_URL") or record.get("url")
    if not isinstance(source_url, str) or not source_url:
        raise SediaDocumentError("SEDIA document source URL is missing")
    name = _first_metadata_value(metadata, "esST_FileName")
    if not isinstance(name, str) or not name:
        raise SediaDocumentError("SEDIA document filename is missing")
    language = _first_metadata_value(metadata, "language")

    return {
        "name": name,
        "media_type": media_type,
        "language": language if isinstance(language, str) and language else None,
        "source_url": source_url,
        "checksum": actual_checksum,
        "source_checksum": checksum.upper(),
        "checksum_verified": checksum_verified,
        "fetched_at": fetched_at,
        "content": content,
    }
