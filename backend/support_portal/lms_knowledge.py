"""Versioned, heading-aware ingestion of the college's LMS help document.

Only public help text belongs here, never learner records or credentials.
The existing pgvector tables are reused; no schema migration is needed.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Any

SOURCE_KEY = "kbc-learningos-help"
EMBEDDING_DIMENSIONS = 1536
MAX_BODY_CHARS = 2400


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def section_audiences(headings: list[str]) -> list[str]:
    """Documentation labels, not access-control grants."""
    for heading in reversed(headings):
        for pattern, audience in (
            (r"^(?:3\.\s+)?Learners\b", "learner"),
            (r"^(?:5\.\s+)?Coaches\b", "coach"),
            (r"^Tutor\b", "tutor"),
            (r"^(?:4\.\s+)?Curriculum\b", "curriculum"),
            (r"^Employer\b", "employer"),
            (r"^Enrolment\b", "enrolment"),
            (r"^Super Admin\b", "admin"),
            (r"^Engagement\b", "engagement"),
            (r"^Audit\b", "audit"),
        ):
            if re.search(pattern, heading, re.I):
                return [audience]
    return ["all"]


def build_chunks(markdown: str, source_name: str) -> list[dict[str, Any]]:
    """Keep heading ancestry and all body lines, including tables and warnings."""
    if not markdown.strip():
        raise ValueError("The LMS Markdown file is empty.")
    headings: list[tuple[int, str]] = []
    sections: list[tuple[list[str], list[str]]] = []
    body: list[str] = []
    fence = None
    for line in markdown.splitlines():
        fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence_match:
            marker = fence_match.group(1)[0]
            fence = None if fence == marker else (marker if fence is None else fence)
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line) if fence is None else None
        if heading:
            if any(part.strip() and part.strip() != "---" for part in body):
                sections.append(([title for _, title in headings], body))
            body = []
            level, title = len(heading.group(1)), heading.group(2)
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, title))
        else:
            body.append(line)
    if any(part.strip() and part.strip() != "---" for part in body):
        sections.append(([title for _, title in headings], body))

    chunks = []
    source_hash = digest(markdown)
    for titles, lines in sections:
        parts: list[str] = []
        pending = ""
        for line in lines:
            # Preserve long lines too; never truncate a source section.
            for offset in range(0, max(1, len(line)), MAX_BODY_CHARS):
                piece = line[offset:offset + MAX_BODY_CHARS]
                candidate = pending + ("\n" if pending else "") + piece
                if pending and len(candidate) > MAX_BODY_CHARS:
                    parts.append(pending.strip())
                    pending = piece
                else:
                    pending = candidate
        if pending.strip():
            parts.append(pending.strip())
        section = " > ".join(titles) or source_name
        audiences = section_audiences(titles)
        guardrail = bool(titles and titles[-1] in {
            "Not live yet", "How to use this document (instructions for the assistant)",
        })
        # The document title heads every section path, and the banner and audience
        # line are near-identical across chunks. Embedding that boilerplate pulls
        # every vector towards the same point: distances for unrelated sections
        # ended up within 0.02 of each other, so nothing ever scored as a good
        # match. Embed the heading trail and body only; keep the full text for
        # display and for the model to read.
        embed_section = " > ".join(titles[1:] or titles) or source_name
        for part_number, part in enumerate(parts, 1):
            text = f"KBC LearningOS help\nSection: {section}\nAudience: {', '.join(audiences)}\n\n{part}"
            embed_text = f"{embed_section}\n\n{part}"
            chunks.append({
                "text": text,
                "embed_text": embed_text,
                "metadata": {
                    "source_key": SOURCE_KEY,
                    "source": source_name,
                    "source_hash": source_hash,
                    "record_type": "chunk",
                    "status": "active",
                    "archived": False,
                    "title": titles[-1] if titles else source_name,
                    "section": section,
                    "audiences": audiences,
                    "guardrail": guardrail,
                    "part": part_number,
                    "parts": len(parts),
                    "chunk_hash": digest(text),
                    # Changing what we embed must force a re-embed, even when the
                    # stored text is identical.
                    "embed_hash": digest(embed_text),
                },
            })
    if not chunks:
        raise ValueError("The Markdown has no help content below its headings.")
    for index, chunk in enumerate(chunks):
        chunk["metadata"].update(chunk_index=index, chunk_count=len(chunks))
    return chunks


def validate_embeddings(vectors: list[list[float]], count: int) -> None:
    if len(vectors) != count:
        raise ValueError("Embedding response does not match the document chunk count.")
    for vector in vectors:
        if len(vector) != EMBEDDING_DIMENSIONS or any(not math.isfinite(v) for v in vector):
            raise ValueError("Embedding must contain 1536 finite numbers.")
        if not any(vector):
            raise ValueError("A zero embedding cannot be used for cosine retrieval.")


def embed_chunks(chunks: list[dict[str, Any]], model: str) -> list[list[float]]:
    from .chatbot import _openai_client

    client = _openai_client()
    vectors = []
    for offset in range(0, len(chunks), 24):
        batch = chunks[offset:offset + 24]
        response = client.embeddings.create(
            model=model,
            # Falls back to the stored text for callers that build chunks by hand.
            input=[item.get("embed_text") or item["text"] for item in batch],
        )
        items = sorted(response.data, key=lambda item: item.index)
        if [item.index for item in items] != list(range(len(batch))):
            raise ValueError("Embedding response indexes are incomplete or duplicated.")
        batch_vectors = [list(item.embedding) for item in items]
        validate_embeddings(batch_vectors, len(batch))
        vectors.extend(batch_vectors)
    return vectors
