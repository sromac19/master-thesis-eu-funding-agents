from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class FundingCallStatus(StrEnum):
    OPEN = "open"
    FORTHCOMING = "forthcoming"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class EligibilityExtractionStatus(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"


class FundingCall(Base):
    __tablename__ = "funding_calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_call_id: Mapped[str] = mapped_column(String(255), nullable=False)
    topic_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    programme: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scope: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_outcomes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_impact: Mapped[str] = mapped_column(Text, nullable=False, default="")
    action_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[FundingCallStatus] = mapped_column(
        Enum(
            FundingCallStatus,
            name="funding_call_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=FundingCallStatus.UNKNOWN,
    )
    opening_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    budget_eur: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    funding_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    applicant_conditions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    consortium_conditions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    trl_min: Mapped[int | None] = mapped_column(nullable=True)
    trl_max: Mapped[int | None] = mapped_column(nullable=True)
    official_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(100), nullable=False, default="unversioned")
    snapshot_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    documents: Mapped[list[CallDocument]] = relationship(
        back_populates="funding_call",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "source",
            "source_call_id",
            "fetched_at",
            name="uq_funding_calls_source_snapshot",
        ),
        CheckConstraint(
            "funding_rate IS NULL OR (funding_rate >= 0 AND funding_rate <= 1)",
            name="ck_funding_calls_funding_rate",
        ),
        CheckConstraint(
            "trl_min IS NULL OR (trl_min >= 1 AND trl_min <= 9)",
            name="ck_funding_calls_trl_min",
        ),
        CheckConstraint(
            "trl_max IS NULL OR (trl_max >= 1 AND trl_max <= 9)",
            name="ck_funding_calls_trl_max",
        ),
        CheckConstraint(
            "trl_min IS NULL OR trl_max IS NULL OR trl_min <= trl_max",
            name="ck_funding_calls_trl_range",
        ),
    )


class CallDocument(Base):
    __tablename__ = "call_documents"
    __table_args__ = (
        UniqueConstraint(
            "funding_call_id",
            "checksum",
            name="uq_call_documents_call_checksum",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    funding_call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("funding_calls.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(1000), nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    source_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    checksum_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    funding_call: Mapped[FundingCall] = relationship(back_populates="documents")
    eligibility_rules: Mapped[list[EligibilityRule]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    chunks: Mapped[list[CallDocumentChunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CallDocumentChunk.chunk_index",
    )


class CallDocumentChunk(Base):
    __tablename__ = "call_document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "call_document_id",
            "chunk_index",
            name="uq_call_document_chunks_document_index",
        ),
        CheckConstraint("chunk_index >= 0", name="ck_call_document_chunks_index"),
        CheckConstraint("page IS NULL OR page >= 1", name="ck_call_document_chunks_page"),
        CheckConstraint(
            "start_offset >= 0 AND end_offset > start_offset",
            name="ck_call_document_chunks_offsets",
        ),
        Index("ix_call_document_chunks_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    call_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("call_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    page: Mapped[int | None] = mapped_column(nullable=True)
    section: Mapped[str | None] = mapped_column(String(500), nullable=True)
    start_offset: Mapped[int] = mapped_column(nullable=False)
    end_offset: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', content)", persisted=True),
        nullable=False,
    )
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    document: Mapped[CallDocument] = relationship(back_populates="chunks")


class DatasetSnapshot(Base):
    __tablename__ = "dataset_snapshots"
    __table_args__ = (
        UniqueConstraint("source", "checksum", name="uq_dataset_snapshot_source_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    local_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    row_counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False, default=dict)
    projects: Mapped[list[HistoricalProject]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan", passive_deletes=True
    )
    euroscivoc_concepts: Mapped[list[EuroSciVocConcept]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan", passive_deletes=True
    )


class HistoricalProject(Base):
    __tablename__ = "historical_projects"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "source_project_id", name="uq_historical_project_snapshot"),
        Index("ix_historical_projects_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    source_project_id: Mapped[str] = mapped_column(String(100), nullable=False)
    acronym: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(2000), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(objective, ''))",
            persisted=True,
        ),
        nullable=False,
    )
    framework_programme: Mapped[str] = mapped_column(String(255), nullable=False)
    funding_scheme: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    eu_contribution: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    snapshot: Mapped[DatasetSnapshot] = relationship(back_populates="projects")
    participants: Mapped[list[Participant]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    topics: Mapped[list[HistoricalProjectTopic]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    classifications: Mapped[list[HistoricalProjectEuroSciVoc]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "source_organisation_id", "role", name="uq_participant_role"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("historical_projects.id", ondelete="CASCADE"), nullable=False
    )
    source_organisation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(1000), nullable=False)
    country: Mapped[str | None] = mapped_column(String(10), nullable=True)
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    sme: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    eu_contribution: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    project: Mapped[HistoricalProject] = relationship(back_populates="participants")


class HistoricalProjectTopic(Base):
    __tablename__ = "historical_project_topics"
    __table_args__ = (UniqueConstraint("project_id", "topic_id", name="uq_project_topic"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("historical_projects.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    project: Mapped[HistoricalProject] = relationship(back_populates="topics")


class HistoricalProjectEuroSciVoc(Base):
    __tablename__ = "historical_project_euroscivoc"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_project_euroscivoc"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("historical_projects.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    project: Mapped[HistoricalProject] = relationship(back_populates="classifications")


class EuroSciVocConcept(Base):
    __tablename__ = "euroscivoc_concepts"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "uri", name="uq_euroscivoc_concept_snapshot"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    notation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    deprecated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    preferred_labels: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)
    alternative_labels: Mapped[dict[str, list[str]]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    snapshot: Mapped[DatasetSnapshot] = relationship(back_populates="euroscivoc_concepts")
    broader_relations: Mapped[list[EuroSciVocBroaderRelation]] = relationship(
        foreign_keys="EuroSciVocBroaderRelation.concept_id",
        back_populates="concept",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    narrower_relations: Mapped[list[EuroSciVocBroaderRelation]] = relationship(
        foreign_keys="EuroSciVocBroaderRelation.broader_concept_id",
        back_populates="broader_concept",
        passive_deletes=True,
    )


class EuroSciVocBroaderRelation(Base):
    __tablename__ = "euroscivoc_broader_relations"
    __table_args__ = (
        UniqueConstraint("concept_id", "broader_concept_id", name="uq_euroscivoc_broader"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("euroscivoc_concepts.id", ondelete="CASCADE"), nullable=False
    )
    broader_concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("euroscivoc_concepts.id", ondelete="CASCADE"), nullable=False
    )
    concept: Mapped[EuroSciVocConcept] = relationship(
        foreign_keys=[concept_id], back_populates="broader_relations"
    )
    broader_concept: Mapped[EuroSciVocConcept] = relationship(
        foreign_keys=[broader_concept_id], back_populates="narrower_relations"
    )


class EligibilityRule(Base):
    __tablename__ = "eligibility_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    call_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_documents.id", ondelete="CASCADE"), nullable=False
    )
    criterion: Mapped[str] = mapped_column(String(100), nullable=False)
    operator: Mapped[str] = mapped_column(String(50), nullable=False)
    expected_value: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    is_hard: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    extraction_status: Mapped[EligibilityExtractionStatus] = mapped_column(
        Enum(
            EligibilityExtractionStatus,
            name="eligibility_extraction_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    page: Mapped[int | None] = mapped_column(nullable=True)
    section: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    human_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    document: Mapped[CallDocument] = relationship(back_populates="eligibility_rules")
