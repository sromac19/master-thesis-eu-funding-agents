"""Adapters for external funding data sources."""

from eu_funding_agents.ingestion.sedia import (
    EXPERIMENTAL_PROGRAMME_IDS,
    SEDIA_ADAPTER_VERSION,
    SediaFetchResult,
    SediaFundingPortalAdapter,
    SediaQualityReport,
    build_quality_report,
    file_sha256,
    normalize_current_sedia_records,
    normalize_sedia_record,
    save_raw_snapshot,
)

__all__ = [
    "EXPERIMENTAL_PROGRAMME_IDS",
    "SEDIA_ADAPTER_VERSION",
    "SediaFetchResult",
    "SediaFundingPortalAdapter",
    "SediaQualityReport",
    "build_quality_report",
    "file_sha256",
    "normalize_current_sedia_records",
    "normalize_sedia_record",
    "save_raw_snapshot",
]
