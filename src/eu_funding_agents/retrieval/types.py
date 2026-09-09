from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class SearchDocument:
    call_id: str
    title: str
    text: str
    programme: str
    official_url: str
    status: str = "unknown"
    opening_date: date | None = None
    deadline: date | None = None
    budget_eur: float | None = None
    funding_rate: float | None = None
    action_type: str | None = None
    applicant_conditions: str = ""
    consortium_conditions: str = ""
    trl_min: int | None = None
    trl_max: int | None = None
    fetched_at: datetime | None = None


@dataclass(frozen=True)
class SearchResult:
    call_id: str
    title: str
    programme: str
    official_url: str
    score: float
    components: dict[str, float] = field(default_factory=dict)
