from __future__ import annotations

from dataclasses import dataclass

import psycopg
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


@dataclass
class LearnerRow:
    external_learner_id: str | None
    full_name: str | None
    email: str
    phone: str | None


class Command(BaseCommand):
    help = "Import learners from the legacy KBC database into the support learners table."

    def handle(self, *args, **options):
        if not settings.LEGACY_DATABASE_URL:
            raise CommandError("LEGACY_DATABASE_URL is missing.")

        with psycopg.connect(settings.LEGACY_DATABASE_URL) as source_connection:
            with source_connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT
                      NULLIF(TRIM("ID"::text), '') AS external_learner_id,
                      NULLIF(TRIM(COALESCE("FullName", CONCAT_WS(' ', "FirstName", "LastName"))), '') AS full_name,
                      LOWER(TRIM("Email")) AS email,
                      NULLIF(TRIM(COALESCE("Learner_Phone", "learner-phone")), '') AS phone
                    FROM kbc_users_data
                    WHERE "Email" IS NOT NULL
                      AND TRIM("Email") <> ''
                    """
                )
                rows = cursor.fetchall()

        deduped: dict[str, LearnerRow] = {}
        for external_learner_id, full_name, email, phone in rows:
            if not email:
                continue
            deduped[email] = LearnerRow(
                external_learner_id=external_learner_id,
                full_name=full_name,
                email=email,
                phone=phone,
            )

        with connection.cursor() as cursor:
            for learner in deduped.values():
                cursor.execute(
                    """
                    INSERT INTO learners (
                      external_learner_id,
                      full_name,
                      email,
                      phone,
                      source,
                      metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (email) DO UPDATE
                    SET
                      external_learner_id = COALESCE(EXCLUDED.external_learner_id, learners.external_learner_id),
                      full_name = COALESCE(EXCLUDED.full_name, learners.full_name),
                      phone = COALESCE(EXCLUDED.phone, learners.phone),
                      source = EXCLUDED.source,
                      metadata = learners.metadata || EXCLUDED.metadata,
                      updated_at = NOW()
                    """,
                    [
                        learner.external_learner_id,
                        learner.full_name,
                        learner.email,
                        learner.phone,
                        "legacy_kbc_users_data",
                        '{"legacy_source": "kbc_users_data"}',
                    ],
                )

        self.stdout.write(self.style.SUCCESS(f"Imported {len(deduped)} learners into the learners table."))
