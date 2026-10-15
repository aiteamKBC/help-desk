"""Import a versioned LMS help document and optionally archive Moodle in place."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from psycopg.types.json import Jsonb
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from config.env import get_env
from support_portal.lms_knowledge import SOURCE_KEY, build_chunks, digest, embed_chunks


def active_rows(cursor):
    cursor.execute(
        """SELECT id,text,metadata,vector_dims(embedding) FROM public.new_lms_knowledge_base
           WHERE metadata->>'source_key'=%s AND COALESCE(metadata->>'archived','false')!='true'
           ORDER BY id""", [SOURCE_KEY],
    )
    return cursor.fetchall()


def matches_version(rows, markdown, chunks, model):
    documents = [r for r in rows if r[2].get("record_type") == "document"]
    stored = [r for r in rows if r[2].get("record_type") == "chunk"]
    if (len(rows) != len(chunks) + 1 or len(documents) != 1
            or documents[0][1] != markdown or documents[0][2].get('status') != 'active'
            or len(stored) != len(chunks)):
        return False
    # embed_hash is part of the identity: the same stored text embedded a
    # different way is a different record and has to be re-embedded.
    expected = {(c["metadata"]["chunk_index"], c["text"], c["metadata"]["embed_hash"]) for c in chunks}
    actual = {(r[2].get("chunk_index"), r[1], r[2].get("embed_hash")) for r in stored}
    return actual == expected and all(
        r[2].get("source_hash") == digest(markdown)
        and r[2].get("embedding_model") == model
        and r[2].get("status") == "active"
        and r[3] == 1536 for r in stored
    )


def moodle_fingerprint(cursor):
    # Verifies that archival preserves every original ID, text and embedding.
    cursor.execute("SELECT id,md5(text),md5(embedding::text) FROM public.moodle_knowledge_base ORDER BY id")
    return cursor.fetchall()


def unrelated_knowledge_fingerprint(cursor):
    cursor.execute(
        """SELECT id,md5(text),md5(metadata::text),md5(embedding::text)
           FROM public.new_lms_knowledge_base
           WHERE metadata->>'source_key' IS DISTINCT FROM %s ORDER BY id""", [SOURCE_KEY],
    )
    return cursor.fetchall()


class Command(BaseCommand):
    help = "Load LMS Markdown into existing Neon pgvector tables. Dry-run unless --apply."

    def add_arguments(self, parser):
        parser.add_argument("source", type=Path)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--archive-moodle", action="store_true")
        parser.add_argument("--expected-host", help="Required for writes; checked against DATABASE_URL hostname.")
        parser.add_argument("--report", type=Path)

    def handle(self, *args, **options):
        source = options["source"].resolve()
        try:
            markdown = source.read_text(encoding="utf-8-sig")
            chunks = build_chunks(markdown, source.name)
        except (OSError, ValueError) as error:
            raise CommandError(str(error)) from error
        # A wrong or partial document must not replace a complete reference.
        roles = Counter(role for c in chunks for role in c["metadata"]["audiences"])
        if not {"learner", "coach", "tutor"} <= roles.keys() or not any(c["metadata"]["guardrail"] for c in chunks):
            raise CommandError("Expected the complete LMS guide, including learner, coach, tutor and limitations sections.")
        url = get_env("DATABASE_URL")
        parsed = urlsplit(url)
        if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
            raise CommandError("The support DATABASE_URL must target PostgreSQL.")
        if options["apply"] and options["expected_host"] != parsed.hostname:
            raise CommandError("--expected-host must match the inspected support DATABASE_URL host.")
        model = settings.OPENAI_EMBEDDING_MODEL
        report = {
            "status": "planned", "target_host": parsed.hostname, "database": parsed.path.lstrip("/"),
            "source": source.name, "source_hash": digest(markdown), "chunks": len(chunks),
            "audiences": dict(roles), "embedding_model": model,
            "archive_moodle": options["archive_moodle"],
        }
        # Direct connection to the same configured endpoint; no environment rewrite.
        host = parsed.hostname.replace("-pooler.", ".")
        with psycopg.connect(url, host=host, connect_timeout=15, autocommit=True) as conn:
            with conn.transaction(), conn.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute("SET LOCAL statement_timeout='30s'")
                for table in ("new_lms_knowledge_base", "moodle_knowledge_base"):
                    cursor.execute("SELECT to_regclass(%s)", ["public." + table])
                    if cursor.fetchone()[0] is None:
                        raise CommandError(f"Existing knowledge table {table} is missing; no changes made.")
                rows = active_rows(cursor)
                current = matches_version(rows, markdown, chunks, model)
                before = moodle_fingerprint(cursor)
                unrelated_before = unrelated_knowledge_fingerprint(cursor)
                cursor.execute("SELECT count(*) FROM public.moodle_knowledge_base WHERE COALESCE(metadata->>'archived','false')!='true'")
                report.update(moodle_rows=len(before), moodle_to_archive=cursor.fetchone()[0], already_imported=current)
            self.stdout.write(json.dumps(report, ensure_ascii=True))
            if options["apply"]:
                # Complete all external embedding calls before opening the write transaction.
                vectors = [] if current else embed_chunks(chunks, model)
                now = datetime.now(timezone.utc).isoformat()
                with conn.transaction(), conn.cursor() as cursor:
                    cursor.execute("SET LOCAL statement_timeout='30s'")
                    cursor.execute("SET LOCAL lock_timeout='10s'")
                    cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [SOURCE_KEY])
                    cursor.execute("LOCK TABLE public.new_lms_knowledge_base, public.moodle_knowledge_base IN SHARE ROW EXCLUSIVE MODE")
                    rows = active_rows(cursor)
                    if not matches_version(rows, markdown, chunks, model):
                        if not vectors:
                            raise CommandError("The knowledge version changed during import. Retry safely.")
                        cursor.execute(
                            """UPDATE public.new_lms_knowledge_base
                               SET metadata=metadata || %s
                               WHERE metadata->>'source_key'=%s
                                 AND COALESCE(metadata->>'archived','false')!='true'""",
                            [Jsonb({"archived": True, "status": "archived", "archived_at": now,
                                    "archive_reason": "Superseded by a verified LMS guide version"}), SOURCE_KEY],
                        )
                        report["previous_lms_records_archived"] = cursor.rowcount
                        metadata = {"source_key": SOURCE_KEY, "source": source.name,
                                    "source_hash": digest(markdown), "record_type": "document",
                                    "archived": False, "status": "active", "imported_at": now,
                                    "embedding_model": model, "chunk_count": len(chunks)}
                        cursor.execute(
                            "INSERT INTO public.new_lms_knowledge_base(text,metadata) VALUES (%s,%s)",
                            [markdown, Jsonb(metadata)],
                        )
                        cursor.executemany(
                            "INSERT INTO public.new_lms_knowledge_base(text,metadata,embedding) VALUES (%s,%s,%s::vector)",
                            [(chunk["text"], Jsonb({**chunk["metadata"], "imported_at": now, "embedding_model": model}),
                              "[" + ",".join(str(v) for v in vector) + "]") for chunk, vector in zip(chunks, vectors)],
                        )
                    if not matches_version(active_rows(cursor), markdown, chunks, model):
                        raise CommandError("LMS source/chunk readback failed; transaction rolled back.")
                    if options["archive_moodle"]:
                        cursor.execute(
                            """UPDATE public.moodle_knowledge_base
                               SET metadata=COALESCE(metadata,'{}'::jsonb) || %s
                               WHERE COALESCE(metadata->>'archived','false')!='true'""",
                            [Jsonb({"archived": True, "status": "archived", "archived_at": now,
                                    "archive_reason": "Replaced by KBC LearningOS help", "replacement_source": SOURCE_KEY})],
                        )
                        report["moodle_archived_now"] = cursor.rowcount
                    if moodle_fingerprint(cursor) != before:
                        raise CommandError("Moodle content changed during import; transaction rolled back.")
                    if unrelated_knowledge_fingerprint(cursor) != unrelated_before:
                        raise CommandError("Unrelated knowledge changed during import; transaction rolled back.")
                    report['unrelated_knowledge_records_preserved'] = len(unrelated_before)
                    report.update(status="applied", verified_chunks=len(chunks), moodle_content_preserved=True)
                # Independent, post-commit readback before reporting completion.
                with conn.transaction(), conn.cursor() as cursor:
                    cursor.execute("SET TRANSACTION READ ONLY")
                    if not matches_version(active_rows(cursor), markdown, chunks, model):
                        raise CommandError("Post-commit knowledge verification failed.")
                    cursor.execute("SELECT count(*) FROM public.moodle_knowledge_base WHERE metadata->>'archived'='true'")
                    report["moodle_archived_total"] = cursor.fetchone()[0]
                    if options["archive_moodle"] and report["moodle_archived_total"] != len(before):
                        raise CommandError("Post-commit Moodle archival verification failed.")
                    report["verified_at"] = datetime.now(timezone.utc).isoformat()
        if options["report"]:
            options["report"].parent.mkdir(parents=True, exist_ok=True)
            options["report"].write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        self.stdout.write(json.dumps(report, ensure_ascii=True))
