from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl


class HealthResponse(BaseModel):
    status: str


class DatabaseHealthResponse(HealthResponse):
    database: str


class CatalogFreshnessResponse(HealthResponse):
    last_fetched_at: datetime
    age_hours: float = Field(ge=0)
    max_age_hours: int = Field(ge=1)
    needs_refresh: bool


class CallStatus(StrEnum):
    OPEN = "open"
    FORTHCOMING = "forthcoming"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class ProjectProfile(BaseModel):
    description: str = Field(min_length=20)
    country: str = Field(min_length=2, max_length=2)
    organisation_type: str
    sectors: list[str] = Field(default_factory=list)
    trl: int | None = Field(default=None, ge=1, le=9)
    requested_budget_eur: float | None = Field(default=None, ge=0)
    has_consortium: bool | None = None
    partner_countries: list[str] = Field(default_factory=list)


class FundingCall(BaseModel):
    call_id: str
    topic_id: str | None = None
    programme: str
    title: str
    description: str = ""
    scope: str = ""
    expected_outcomes: str = ""
    expected_impact: str = ""
    action_type: str | None = None
    status: CallStatus = CallStatus.UNKNOWN
    opening_date: date | None = None
    deadline: date | None = None
    budget_eur: float | None = Field(default=None, ge=0)
    funding_rate: float | None = Field(default=None, ge=0, le=1)
    applicant_conditions: str = ""
    consortium_conditions: str = ""
    trl_min: int | None = Field(default=None, ge=1, le=9)
    trl_max: int | None = Field(default=None, ge=1, le=9)
    official_url: HttpUrl
    fetched_at: datetime
    adapter_version: str
    snapshot_checksum: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class CriterionResult(BaseModel):
    criterion: str
    status: str
    explanation: str
    evidence: str | None = None
    source_url: HttpUrl | None = None


class RecommendationPreviewRequest(BaseModel):
    profile: ProjectProfile
    top_k: int = Field(default=5, ge=1, le=20)
    as_of: date


class EvidenceCitation(BaseModel):
    document_name: str
    source_url: HttpUrl
    page: int | None
    section: str | None
    excerpt: str
    document_checksum: str = Field(pattern=r"^[0-9A-Fa-f]{64}$")
    content_checksum: str = Field(pattern=r"^[0-9A-Fa-f]{64}$")


class RecommendationItem(BaseModel):
    call_id: str
    programme: str
    title: str
    action_type: str | None = None
    call_status: CallStatus
    opening_date: date | None = None
    deadline: date
    days_remaining: int = Field(ge=0)
    budget_eur: float | None = Field(default=None, ge=0)
    funding_rate: float | None = Field(default=None, ge=0, le=1)
    applicant_conditions: str = ""
    consortium_conditions: str = ""
    trl_min: int | None = Field(default=None, ge=1, le=9)
    trl_max: int | None = Field(default=None, ge=1, le=9)
    fetched_at: datetime
    relevance_score: float
    eligibility_status: str
    official_url: HttpUrl
    reasons_for: list[str]
    reasons_against: list[str]
    missing_information: list[str]
    evidence: list[EvidenceCitation] = Field(default_factory=list)


class RecommendationPreviewResponse(BaseModel):
    generated_at: datetime
    as_of: date
    method: str
    recommendations: list[RecommendationItem]
    disclaimer: str


class HistoricalSimilarityRequest(BaseModel):
    project_description: str = Field(min_length=20)
    top_k: int = Field(default=3, ge=1, le=10)


class SimilarProjectItem(BaseModel):
    project_id: str
    title: str
    acronym: str | None
    framework_programme: str
    similarity_score: float
    official_url: HttpUrl


class PartnerSignalItem(BaseModel):
    role: str
    country: str | None
    similar_project_count: int
    explanation: str


class HistoricalSimilarityResponse(BaseModel):
    method: str
    similar_projects: list[SimilarProjectItem]
    partner_signals: list[PartnerSignalItem]
    limitation: str
