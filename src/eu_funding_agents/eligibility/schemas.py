from __future__ import annotations

from enum import StrEnum
from urllib.parse import urlparse

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class CriterionType(StrEnum):
    COUNTRY_ALLOWED = "country_allowed"
    ORGANISATION_TYPE_ALLOWED = "organisation_type_allowed"
    SME_REQUIRED = "sme_required"
    MIN_CONSORTIUM_SIZE = "min_consortium_size"
    MIN_TRL = "min_trl"
    MAX_TRL = "max_trl"


class RuleOperator(StrEnum):
    IN = "in"
    EQUALS = "equals"
    GREATER_THAN_OR_EQUAL = "gte"
    LESS_THAN_OR_EQUAL = "lte"


class ExtractionStatus(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"


class RuleOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class ExtractedCriterion(BaseModel):
    criterion: CriterionType
    operator: RuleOperator
    expected_value: str | int | bool | list[str] | None
    is_hard: bool = True
    applicable: bool | None = None
    extraction_status: ExtractionStatus
    evidence_text: str | None = Field(default=None, min_length=1)
    page: int | None = Field(default=None, ge=1)
    section: str | None = Field(default=None, min_length=1, max_length=500)
    # Keep the structured-output schema to plain JSON Schema primitives. OpenAI
    # rejects Pydantic's `format: uri`, so URL syntax is enforced after parsing.
    source_url: str = Field(min_length=1, max_length=2048)
    confidence: float = Field(ge=0, le=1)
    human_confirmed: bool = False

    @field_validator("source_url")
    @classmethod
    def require_https_source_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("source_url must be a valid HTTPS URL")
        return value

    @model_validator(mode="after")
    def require_evidence_for_supported_rule(self) -> ExtractedCriterion:
        if self.extraction_status is ExtractionStatus.SUPPORTED and not self.evidence_text:
            raise ValueError("supported criteria require evidence_text")
        return self


class EligibilityExtraction(BaseModel):
    criteria: list[ExtractedCriterion]
    missing_information: list[str] = Field(default_factory=list)


class OrganisationProfile(BaseModel):
    country: str | None = Field(default=None, min_length=2, max_length=2)
    organisation_type: str | None = Field(default=None, min_length=1, max_length=100)
    sme: bool | None = None
    consortium_size: int | None = Field(default=None, ge=1)


class ProjectProfile(BaseModel):
    description: str | None = Field(default=None, min_length=20)
    trl: int | None = Field(default=None, ge=1, le=9)


class RuleResult(BaseModel):
    criterion: CriterionType
    outcome: RuleOutcome
    is_hard: bool
    actual_value: str | int | bool | None
    expected_value: str | int | bool | list[str] | None
    reason: str
    evidence_text: str | None
    source_url: HttpUrl
