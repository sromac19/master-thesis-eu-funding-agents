from __future__ import annotations

import uuid
from typing import Any

from eu_funding_agents.db.models import CallDocument, CallDocumentChunk
from eu_funding_agents.documents.chunks import chunk_document_pages, chunk_document_text
from eu_funding_agents.documents.manifest import ManifestDocument
from eu_funding_agents.documents.pdf import ParsedPdf, parse_pdf


def attach_document_chunks(
    document: CallDocument,
    *,
    section: str | None = None,
) -> int:
    if document.chunks:
        return 0
    chunks = chunk_document_text(document.content, section=section)
    document.chunks.extend(
        CallDocumentChunk(
            chunk_index=chunk.chunk_index,
            page=chunk.page,
            section=chunk.section,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            content=chunk.content,
            content_checksum=chunk.content_checksum,
        )
        for chunk in chunks
    )
    return len(chunks)


def build_sedia_call_document(document_data: dict[str, Any]) -> CallDocument:
    document = CallDocument(**document_data)
    attach_document_chunks(document, section="SEDIA embedded document")
    return document


def build_pdf_call_document(
    manifest_document: ManifestDocument,
    *,
    funding_call_id: uuid.UUID,
    parsed_pdf: ParsedPdf | None = None,
) -> CallDocument:
    parsed = parsed_pdf or parse_pdf(manifest_document.path)
    document = CallDocument(
        funding_call_id=funding_call_id,
        name=manifest_document.title,
        media_type=manifest_document.media_type,
        language="en",
        source_url=manifest_document.source_url,
        checksum=manifest_document.checksum,
        source_checksum=manifest_document.checksum,
        checksum_verified=True,
        fetched_at=manifest_document.fetched_at,
        content=parsed.text_with_page_markers,
    )
    document.chunks.extend(
        CallDocumentChunk(
            chunk_index=chunk.chunk_index,
            page=chunk.page,
            section=manifest_document.title,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            content=chunk.content,
            content_checksum=chunk.content_checksum,
        )
        for chunk in chunk_document_pages(parsed.pages)
    )
    return document
