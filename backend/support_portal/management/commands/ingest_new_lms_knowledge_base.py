from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from support_portal.ai.openai_service import EMBEDDING_MODEL, create_embedding

TABLE_NAME = "new_lms_knowledge_base"
MAX_CHUNK_CHARS = 1200
CHUNK_OVERLAP_CHARS = 180


def normalize_text(value: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", value.replace("\r\n", "\n").replace("\r", "\n")).strip()


def split_sections(document: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title = "Kent Business College Support Portal Documentation"
    current_lines: list[str] = []

    for line in document.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading and current_lines:
            sections.append((current_title, "\n".join(current_lines).strip()))
            current_lines = []
        if heading:
            current_title = heading.group(2).strip()
        current_lines.append(line)

    if current_lines:
        sections.append((current_title, "\n".join(current_lines).strip()))

    return [(title, body) for title, body in sections if body]


def chunk_section(title: str, text: str) -> list[dict[str, str | int]]:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    chunks: list[dict[str, str | int]] = []
    current = ""

    def push(value: str) -> None:
        content = value.strip()
        if not content:
            return
        chunks.append({
            "title": title,
            "text": content,
            "char_count": len(content),
        })

    for paragraph in paragraphs:
        if len(paragraph) > MAX_CHUNK_CHARS:
            push(current)
            current = ""
            start = 0
            while start < len(paragraph):
                end = min(start + MAX_CHUNK_CHARS, len(paragraph))
                push(paragraph[start:end])
                if end == len(paragraph):
                    break
                start = max(end - CHUNK_OVERLAP_CHARS, start + 1)
            continue

        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) > MAX_CHUNK_CHARS:
            push(current)
            current = paragraph
        else:
            current = candidate

    push(current)
    return chunks


def build_chunks(document: str) -> list[dict[str, str | int]]:
    chunks: list[dict[str, str | int]] = []
    for title, section_text in split_sections(document):
        chunks.extend(chunk_section(title, section_text))
    return chunks


def ensure_table() -> None:
    with connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id BIGSERIAL PRIMARY KEY,
                text TEXT NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                embedding vector(1536),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cursor.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_embedding
            ON {TABLE_NAME}
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
            """
        )


class Command(BaseCommand):
    help = "Ingest the new LMS documentation into the PGVector-backed new_lms_knowledge_base table."

    def add_arguments(self, parser):
        parser.add_argument("source", help="Path to the new LMS documentation text/markdown file.")
        parser.add_argument("--no-reset", action="store_true", help="Append to the table instead of replacing existing rows.")
        parser.add_argument("--test-query", default="", help="Run a retrieval test query after ingestion.")
        parser.add_argument("--limit", type=int, default=3, help="Number of retrieval rows to print for --test-query.")

    def handle(self, *args, **options):
        source_path = Path(options["source"]).expanduser().resolve()
        if not source_path.exists():
            raise CommandError(f"Documentation file not found: {source_path}")

        document = normalize_text(source_path.read_text(encoding="utf-8"))
        if not document:
            raise CommandError("Documentation file is empty.")

        chunks = build_chunks(document)
        if not chunks:
            raise CommandError("No chunks were produced from the documentation.")

        ensure_table()

        source_hash = hashlib.sha256(document.encode("utf-8")).hexdigest()
        if not options["no_reset"]:
            with connection.cursor() as cursor:
                cursor.execute(f"TRUNCATE TABLE {TABLE_NAME} RESTART IDENTITY")

        for index, chunk in enumerate(chunks, start=1):
            text = str(chunk["text"])
            metadata = {
                "title": str(chunk["title"]),
                "source": source_path.name,
                "source_hash": source_hash,
                "chunk_index": index,
                "chunk_count": len(chunks),
                "embedding_model": EMBEDDING_MODEL,
                "char_count": int(chunk["char_count"]),
            }
            embedding = create_embedding(text)
            vector_literal = "[" + ",".join(str(value) for value in embedding) + "]"

            with connection.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO {TABLE_NAME} (text, metadata, embedding) VALUES (%s, %s::jsonb, %s::vector)",
                    [text, json.dumps(metadata), vector_literal],
                )

            if index % 10 == 0 or index == len(chunks):
                self.stdout.write(f"Ingested {index}/{len(chunks)} chunks...")

        self.stdout.write(self.style.SUCCESS(f"Ingested {len(chunks)} chunks into {TABLE_NAME}."))

        test_query = str(options["test_query"] or "").strip()
        if test_query:
            query_embedding = create_embedding(test_query)
            query_vector = "[" + ",".join(str(value) for value in query_embedding) + "]"
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT text, metadata, embedding <=> %s::vector AS distance
                    FROM {TABLE_NAME}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    [query_vector, query_vector, max(1, min(int(options["limit"]), 5))],
                )
                rows = cursor.fetchall()

            self.stdout.write("Retrieval test results:")
            for result_index, row in enumerate(rows, start=1):
                metadata = row[1] if isinstance(row[1], dict) else {}
                title = metadata.get("title") or f"Result {result_index}"
                preview = re.sub(r"\s+", " ", row[0] or "")[:220]
                self.stdout.write(f"{result_index}. {title} | distance={float(row[2]):.4f} | {preview}")
