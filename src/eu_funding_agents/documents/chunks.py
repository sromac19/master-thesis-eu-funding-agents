from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentChunk:
    chunk_index: int
    page: int | None
    section: str | None
    start_offset: int
    end_offset: int
    content: str
    content_checksum: str


def normalize_document_text(text: str) -> str:
    return " ".join(text.split())


def chunk_document_text(
    text: str,
    *,
    max_chars: int = 1200,
    overlap_chars: int = 150,
    page: int | None = None,
    section: str | None = None,
    start_index: int = 0,
) -> list[DocumentChunk]:
    if max_chars < 100:
        raise ValueError("max_chars must be at least 100")
    if not 0 <= overlap_chars < max_chars:
        raise ValueError("overlap_chars must be non-negative and smaller than max_chars")
    normalized = normalize_document_text(text)
    words = list(re.finditer(r"\S+", normalized))
    if not words:
        return []

    chunks: list[DocumentChunk] = []
    first_word = 0
    while first_word < len(words):
        last_word = first_word
        while (
            last_word + 1 < len(words)
            and words[last_word + 1].end() - words[first_word].start() <= max_chars
        ):
            last_word += 1
        start_offset = words[first_word].start()
        end_offset = words[last_word].end()
        content = normalized[start_offset:end_offset]
        chunks.append(
            DocumentChunk(
                chunk_index=start_index + len(chunks),
                page=page,
                section=section,
                start_offset=start_offset,
                end_offset=end_offset,
                content=content,
                content_checksum=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            )
        )
        if last_word == len(words) - 1:
            break
        next_target = max(end_offset - overlap_chars, start_offset + 1)
        next_word = last_word + 1
        for index in range(first_word + 1, last_word + 1):
            if words[index].start() >= next_target:
                next_word = index
                break
        first_word = next_word
    return chunks


def chunk_document_pages(
    pages: tuple[str, ...],
    *,
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    for page_number, page_text in enumerate(pages, start=1):
        chunks.extend(
            chunk_document_text(
                page_text,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
                page=page_number,
                start_index=len(chunks),
            )
        )
    return chunks
