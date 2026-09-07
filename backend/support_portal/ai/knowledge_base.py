from __future__ import annotations

import json
from typing import Any

from django.db import connection

from .openai_service import create_embedding

ROUTE_TABLES = {
    "teams": "teams_knowledge_base",
    "aptem": "kbc_knowledge_base",
    "moodle": "new_lms_knowledge_base",
}


def search_knowledge_base(route: str, message: str, limit: int = 3) -> list[dict[str, Any]]:
    table = ROUTE_TABLES.get(route)
    if not table or not message.strip():
        return []

    embedding = create_embedding(message)
    vector_literal = "[" + ",".join(str(value) for value in embedding) + "]"

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT text, metadata, embedding <=> %s::vector AS distance
            FROM {table}
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            [vector_literal, vector_literal, max(1, min(int(limit), 5))],
        )
        rows = cursor.fetchall()

    results = []
    for row in rows:
        metadata = row[1] or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        results.append({
            "text": row[0] or "",
            "metadata": metadata if isinstance(metadata, dict) else {},
            "distance": float(row[2]) if row[2] is not None else None,
        })
    return results


def format_context(results: list[dict[str, Any]]) -> str:
    chunks = []
    for index, item in enumerate(results, start=1):
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        title = metadata.get("title") or metadata.get("article_id") or f"Result {index}"
        url = metadata.get("url") or ""
        chunks.append(f"Source {index}: {title}\nURL: {url}\nContent:\n{str(item.get('text') or '').strip()[:1800]}")
    return "\n\n".join(chunks)
