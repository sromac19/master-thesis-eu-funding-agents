from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Self

import httpx

SEDIA_ADAPTER_VERSION = "0.4.0"
SEDIA_SEARCH_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
SEDIA_API_KEY = "SEDIA"
SEDIA_OPEN_STATUS_CODES = ("31094501", "31094502")
SEDIA_GRANT_TYPE_CODES = ("1", "2", "8")
PROGRAMME_NAMES = {
    "111111": "EU External Action (EuropeAid)",
    "43108390": "Horizon Europe",
    "43152860": "Digital Europe",
    "43251567": "Connecting Europe Facility",
    "43251589": "Citizens, Equality, Rights and Values",
    "43251814": "Creative Europe",
    "43252368": "Internal Security Fund",
    "43252386": "Justice Programme",
    "43252405": "LIFE Programme",
    "43252433": "Pericles IV",
    "43252449": "Research Fund for Coal and Steel",
    "43252476": "Single Market Programme",
    "43252517": "Social Prerogatives and Specific Competencies Lines",
    "43254019": "European Social Fund Plus",
    "43254037": "European Solidarity Corps",
    "43298916": "Euratom Research and Training Programme",
    "43353764": "Erasmus+",
    "43637601": "Pilot Projects and Preparatory Actions",
    "44181033": "European Defence Fund",
    "44416173": "Interregional Innovation Investments Instrument",
    "44773066": "Just Transition Mechanism Public Sector Loan Facility",
    "45532249": "EU bodies and agencies",
}
EXPERIMENTAL_PROGRAMME_IDS = tuple(PROGRAMME_NAMES)


class SediaApiError(RuntimeError):
    """Raised when SEDIA cannot return a valid search response."""


@dataclass(frozen=True)
class SediaFetchResult:
    records: list[dict[str, Any]]
    total_results: int
    fetched_at: datetime
    raw_payload: dict[str, Any]
    pages_fetched: int = 1
    duplicate_records: int = 0
    source_mode: str = "live"
    adapter_version: str = SEDIA_ADAPTER_VERSION


@dataclass(frozen=True)
class SediaQualityReport:
    fetched_records: int
    normalized_records: int
    current_records: int
    excluded_non_current_records: int
    duplicate_records: int
    missing_deadline_records: int
    missing_action_type_records: int
    missing_scope_records: int
    missing_applicant_conditions_records: int


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if cleaned:
            self.parts.append(cleaned)


def _html_text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    return " ".join(parser.parts)


def _first_value(metadata: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, list):
            if value:
                return value[0]
        elif value not in (None, ""):
            return value
    return None


def _all_values(metadata: dict[str, Any], key: str) -> list[Any]:
    value = metadata.get(key)
    if isinstance(value, list):
        return value
    return [value] if value not in (None, "") else []


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    if normalized.endswith("+0000"):
        normalized = f"{normalized[:-5]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _parse_decimal(value: Any) -> Decimal | None:
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    return None


def _extract_budget(metadata: dict[str, Any]) -> Decimal | None:
    raw_budget = _first_value(metadata, "budget", "budgetAmount", "totalBudget")
    budget = _parse_decimal(raw_budget)
    if budget is not None:
        return budget

    overview = _first_value(metadata, "budgetOverview")
    if not isinstance(overview, str):
        return None
    try:
        parsed = json.loads(overview)
    except json.JSONDecodeError:
        return None
    amounts: list[Decimal] = []
    for actions in parsed.get("budgetTopicActionMap", {}).values():
        for action in actions:
            value = action.get("budgetYearMap")
            if isinstance(value, dict):
                amounts.extend(
                    amount
                    for amount in (_parse_decimal(item) for item in value.values())
                    if amount is not None
                )
    return sum(amounts, Decimal(0)) if amounts else None


def _derive_status(
    opening_date: date | None,
    deadline: date | None,
    today: date,
) -> str:
    if deadline is not None and deadline < today:
        return "closed"
    if opening_date is None or deadline is None:
        return "unknown"
    if opening_date > today:
        return "forthcoming"
    return "open"


def _select_deadline(metadata: dict[str, Any], today: date) -> date | None:
    """Select the first deadline that has not passed as of ``today``.

    SEDIA may return multiple stages, such as a past 2025 deadline followed by
    a valid 2026 deadline. The minimum date from the non-past deadlines is the
    current stage; if every deadline is past, the latest past date is retained
    so the record can be classified as closed.
    """
    deadlines = [
        parsed.date()
        for value in _all_values(metadata, "deadlineDate")
        if (parsed := _parse_datetime(value)) is not None
    ]
    if not deadlines:
        return None
    future_deadlines = [deadline for deadline in deadlines if deadline >= today]
    return min(future_deadlines) if future_deadlines else max(deadlines)


def normalize_sedia_record(
    record: dict[str, Any],
    *,
    fetched_at: datetime,
    today: date | None = None,
    adapter_version: str = SEDIA_ADAPTER_VERSION,
    snapshot_checksum: str | None = None,
) -> dict[str, Any]:
    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        raise TypeError("SEDIA record has no metadata object")

    opening_datetime = _parse_datetime(_first_value(metadata, "startDate"))
    opening_date = opening_datetime.date() if opening_datetime else None
    effective_today = today or datetime.now(UTC).date()
    deadline = _select_deadline(metadata, effective_today)
    programme_id = str(_first_value(metadata, "frameworkProgramme") or "")
    source_call_id = str(
        _first_value(metadata, "identifier", "callIdentifier", "REFERENCE")
        or record.get("reference", "")
    )
    title = str(
        _first_value(metadata, "title") or record.get("summary") or record.get("content") or ""
    )
    description = _html_text(
        record.get("content") or _first_value(metadata, "description") or record.get("summary")
    )
    scope = _html_text(_first_value(metadata, "destinationDetails"))
    applicant_conditions = _html_text(_first_value(metadata, "beneficiaryAdministration"))
    raw_action_type = _first_value(metadata, "type")
    official_url = record.get("url") or _first_value(metadata, "url")
    if not source_call_id or not title or not official_url:
        raise ValueError("SEDIA record is missing call ID, title, or official URL")

    return {
        "source_call_id": source_call_id,
        "topic_id": source_call_id,
        "programme": PROGRAMME_NAMES.get(programme_id, programme_id or "UNKNOWN"),
        "title": title,
        "description": description,
        "scope": scope,
        "expected_outcomes": "",
        "expected_impact": "",
        "action_type": f"sedia_type:{raw_action_type}" if raw_action_type is not None else None,
        "status": _derive_status(opening_date, deadline, effective_today),
        "opening_date": opening_date,
        "deadline": deadline,
        "budget_eur": _extract_budget(metadata),
        "funding_rate": None,
        "applicant_conditions": applicant_conditions,
        "consortium_conditions": "",
        "trl_min": None,
        "trl_max": None,
        "official_url": str(official_url),
        "source": "sedia",
        "fetched_at": fetched_at,
        "adapter_version": adapter_version,
        "snapshot_checksum": snapshot_checksum,
        "document_checksum": record.get("checksum") or _first_value(metadata, "esST_checksum"),
    }


def normalize_current_sedia_records(
    records: list[dict[str, Any]],
    *,
    fetched_at: datetime,
    today: date | None = None,
    adapter_version: str = SEDIA_ADAPTER_VERSION,
    snapshot_checksum: str | None = None,
) -> list[dict[str, Any]]:
    normalized = [
        normalize_sedia_record(
            record,
            fetched_at=fetched_at,
            today=today,
            adapter_version=adapter_version,
            snapshot_checksum=snapshot_checksum,
        )
        for record in records
    ]
    current = [record for record in normalized if record["status"] in {"open", "forthcoming"}]
    unique: dict[str, dict[str, Any]] = {}
    for record in current:
        unique.setdefault(str(record["source_call_id"]), record)
    return list(unique.values())


def build_quality_report(
    raw_records: list[dict[str, Any]],
    normalized_records: list[dict[str, Any]],
) -> SediaQualityReport:
    source_ids = [str(record["source_call_id"]) for record in normalized_records]
    duplicate_records = len(source_ids) - len(set(source_ids))
    current_records = [
        record for record in normalized_records if record["status"] in {"open", "forthcoming"}
    ]
    unique_current_ids = {str(record["source_call_id"]) for record in current_records}
    return SediaQualityReport(
        fetched_records=len(raw_records),
        normalized_records=len(normalized_records),
        current_records=len(unique_current_ids),
        excluded_non_current_records=len(normalized_records) - len(current_records),
        duplicate_records=duplicate_records,
        missing_deadline_records=sum(record["deadline"] is None for record in normalized_records),
        missing_action_type_records=sum(
            record.get("action_type") is None for record in normalized_records
        ),
        missing_scope_records=sum(not record.get("scope") for record in normalized_records),
        missing_applicant_conditions_records=sum(
            not record.get("applicant_conditions") for record in normalized_records
        ),
    )


def load_sedia_snapshot(path: Path) -> SediaFetchResult:
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    if snapshot.get("source") != "sedia" or not isinstance(snapshot.get("response"), dict):
        raise SediaApiError("File is not a SEDIA raw snapshot")
    response = snapshot["response"]
    pages = response.get("pages")
    if pages is None:
        pages = [response]
    if not isinstance(pages, list) or not pages:
        raise SediaApiError("SEDIA snapshot has no response pages")

    records_by_id: dict[str, dict[str, Any]] = {}
    duplicate_records = 0
    expected_total: int | None = None
    for page_number, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            raise SediaApiError(f"SEDIA snapshot page {page_number} is invalid")
        page_records, total_results = SediaFundingPortalAdapter._validate_page(
            page, page_number=page_number
        )
        if expected_total is None:
            expected_total = total_results
        elif total_results != expected_total:
            raise SediaApiError("SEDIA totalResults changed inside raw snapshot")
        for record in page_records:
            identity = SediaFundingPortalAdapter._record_identity(record)
            if identity in records_by_id:
                duplicate_records += 1
                continue
            records_by_id[identity] = record
    fetched_at = _parse_datetime(snapshot.get("fetched_at"))
    if fetched_at is None:
        raise SediaApiError("SEDIA snapshot has an invalid fetched_at")
    return SediaFetchResult(
        records=list(records_by_id.values()),
        total_results=expected_total or 0,
        fetched_at=fetched_at,
        raw_payload=response,
        pages_fetched=len(pages),
        duplicate_records=duplicate_records,
        source_mode="fallback_snapshot",
        adapter_version=str(snapshot.get("adapter_version") or "legacy-unrecorded"),
    )


class SediaFundingPortalAdapter:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
        rate_limit_seconds: float = 0.25,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("SEDIA timeout must be positive")
        if max_retries < 0:
            raise ValueError("SEDIA max retries cannot be negative")
        if backoff_seconds < 0 or rate_limit_seconds < 0:
            raise ValueError("SEDIA delays cannot be negative")
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = client is None
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._rate_limit_seconds = rate_limit_seconds
        self._sleep = sleep

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def fetch_open_grants(self, *, limit: int = 20, today: date | None = None) -> SediaFetchResult:
        if not 1 <= limit <= 20:
            raise ValueError("The initial SEDIA fetch is limited to 20 records")

        effective_today = today or datetime.now(UTC).date()

        query = self._build_open_grants_query(today=effective_today)
        files = self._build_search_files(query)
        params = {
            "apiKey": SEDIA_API_KEY,
            "text": "***",
            "pageSize": str(limit),
            "pageNumber": "1",
        }
        payload = self._request(params=params, files=files)
        records, total_results = self._validate_page(payload, page_number=1)
        return SediaFetchResult(
            records=records,
            total_results=total_results,
            fetched_at=datetime.now(UTC),
            raw_payload=payload,
        )

    def fetch_open_grants_paginated(
        self,
        *,
        programme_ids: tuple[str, ...] | None = EXPERIMENTAL_PROGRAMME_IDS,
        page_size: int = 100,
        max_pages: int = 20,
        today: date | None = None,
    ) -> SediaFetchResult:
        if not 1 <= page_size <= 100:
            raise ValueError("SEDIA page size must be between 1 and 100")
        if not 1 <= max_pages <= 100:
            raise ValueError("SEDIA max pages must be between 1 and 100")
        if programme_ids == ():
            raise ValueError("At least one SEDIA programme ID is required")

        effective_today = today or datetime.now(UTC).date()
        query = self._build_open_grants_query(
            today=effective_today,
            programme_ids=programme_ids,
        )
        files = self._build_search_files(query)
        pages: list[dict[str, Any]] = []
        records_by_id: dict[str, dict[str, Any]] = {}
        duplicate_records = 0
        expected_total: int | None = None

        for page_number in range(1, max_pages + 1):
            params = {
                "apiKey": SEDIA_API_KEY,
                "text": "***",
                "pageSize": str(page_size),
                "pageNumber": str(page_number),
            }
            payload = self._request(params=params, files=files)
            page_records, total_results = self._validate_page(payload, page_number=page_number)
            if expected_total is None:
                expected_total = total_results
            elif total_results != expected_total:
                raise SediaApiError("SEDIA totalResults changed during paginated fetch")

            pages.append(payload)
            for record in page_records:
                record_id = self._record_identity(record)
                if record_id in records_by_id:
                    duplicate_records += 1
                    continue
                records_by_id[record_id] = record

            raw_count = sum(len(page["results"]) for page in pages)
            if raw_count >= total_results:
                break
            if not page_records:
                raise SediaApiError("SEDIA pagination ended before totalResults was reached")
            if page_number == max_pages:
                raise SediaApiError("SEDIA result exceeds the configured maximum page count")
            self._sleep(self._rate_limit_seconds)

        fetched_at = datetime.now(UTC)
        return SediaFetchResult(
            records=list(records_by_id.values()),
            total_results=expected_total or 0,
            fetched_at=fetched_at,
            raw_payload={
                "programmeIds": list(programme_ids) if programme_ids is not None else None,
                "pageSize": page_size,
                "pages": pages,
            },
            pages_fetched=len(pages),
            duplicate_records=duplicate_records,
        )

    @staticmethod
    def _build_open_grants_query(
        *,
        today: date,
        programme_ids: tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        must: list[dict[str, Any]] = [
            {"terms": {"status": list(SEDIA_OPEN_STATUS_CODES)}},
            {"terms": {"type": list(SEDIA_GRANT_TYPE_CODES)}},
            {"range": {"deadlineDate": {"gte": f"{today.isoformat()}T00:00:00.000Z"}}},
        ]
        if programme_ids is not None:
            must.append({"terms": {"frameworkProgramme": list(programme_ids)}})
        return {
            "bool": {
                "must": must,
            }
        }

    @staticmethod
    def _build_search_files(query: dict[str, Any]) -> dict[str, Any]:
        return {
            "query": ("blob", json.dumps(query), "application/json"),
            "sort": (
                "blob",
                json.dumps({"field": "lastModified", "order": "DESC"}),
                "application/json",
            ),
            "languages": ("blob", json.dumps(["en"]), "application/json"),
        }

    @staticmethod
    def _validate_page(
        payload: dict[str, Any],
        *,
        page_number: int,
    ) -> tuple[list[dict[str, Any]], int]:
        records = payload.get("results")
        if not isinstance(records, list):
            raise SediaApiError(f"SEDIA page {page_number} has no results list")
        if not all(isinstance(record, dict) for record in records):
            raise SediaApiError(f"SEDIA page {page_number} contains an invalid result")
        total_results = payload.get("totalResults", 0)
        if not isinstance(total_results, int) or total_results < 0:
            raise SediaApiError(f"SEDIA page {page_number} has an invalid totalResults value")
        return records, total_results

    @staticmethod
    def _record_identity(record: dict[str, Any]) -> str:
        metadata = record.get("metadata")
        if not isinstance(metadata, dict):
            raise SediaApiError("SEDIA result has no metadata object")
        identity = _first_value(metadata, "identifier", "callIdentifier", "REFERENCE")
        identity = identity or record.get("reference")
        if not isinstance(identity, str) or not identity:
            raise SediaApiError("SEDIA result has no call/topic identifier")
        return identity

    def _request(self, *, params: dict[str, str], files: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(
                    SEDIA_SEARCH_URL,
                    params=params,
                    files=files,
                    timeout=self._timeout_seconds,
                )
                if (
                    response.status_code == 429 or response.status_code >= 500
                ) and attempt < self._max_retries:
                    self._sleep(self._backoff_seconds * (2**attempt))
                    continue
                response.raise_for_status()
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt >= self._max_retries:
                    raise SediaApiError("SEDIA request failed") from exc
                self._sleep(self._backoff_seconds * (2**attempt))
                continue
            except httpx.HTTPError as exc:
                raise SediaApiError("SEDIA request failed") from exc

            try:
                payload = response.json()
            except ValueError as exc:
                raise SediaApiError("SEDIA response is not valid JSON") from exc
            if not isinstance(payload, dict):
                raise SediaApiError("SEDIA response is not a JSON object")
            return payload
        raise SediaApiError("SEDIA request failed")


def save_raw_snapshot(
    payload: dict[str, Any],
    *,
    directory: Path,
    fetched_at: datetime,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = fetched_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"sedia_funding_tenders_{timestamp}.json"
    snapshot = {
        "source": "sedia",
        "adapter_version": SEDIA_ADAPTER_VERSION,
        "fetched_at": fetched_at.isoformat(),
        "response": payload,
    }
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
