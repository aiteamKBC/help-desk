from __future__ import annotations

import json
import re
from contextlib import nullcontext

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from support_portal.roles import ACCOUNT_SCOPE_REQUESTER, ROLE_USER
from support_portal.services import normalize_account_email

USERNAME_SANITIZE_PATTERN = re.compile(r"[^a-z0-9]+")


def sanitize_support_account_username(value: str) -> str:
    normalized_value = (value or "").strip().lower()
    if not normalized_value:
        return "user"

    sanitized_value = USERNAME_SANITIZE_PATTERN.sub("-", normalized_value).strip("-")
    return sanitized_value or "user"


def build_unique_support_account_username(
    *,
    email: str,
    full_name: str,
    existing_usernames: set[str],
) -> str:
    email_local_part = email.split("@", 1)[0] if email else ""
    base_username = (
        sanitize_support_account_username(email_local_part)
        or sanitize_support_account_username(full_name)
        or "user"
    )

    candidate_username = base_username
    candidate_number = 2

    while candidate_username in existing_usernames:
        candidate_username = f"{base_username}-{candidate_number}"
        candidate_number += 1

    existing_usernames.add(candidate_username)
    return candidate_username


class Command(BaseCommand):
    help = "Create requester support accounts for every learner email that is not already represented."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be inserted without writing to support_accounts.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, full_name, email, source, metadata
                FROM learners
                WHERE email IS NOT NULL
                  AND TRIM(email) <> ''
                ORDER BY id ASC
                """
            )
            learner_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT username, email
                FROM support_accounts
                """
            )
            existing_account_rows = cursor.fetchall()

        existing_usernames = {
            sanitize_support_account_username(str(username))
            for username, _email in existing_account_rows
            if username
        }
        existing_emails = {
            normalize_account_email(email)
            for _username, email in existing_account_rows
            if email
        }

        inserted_count = 0
        linked_count = 0
        skipped_existing_count = 0
        skipped_invalid_count = 0
        prepared_rows: list[list[object]] = []

        for _learner_id, full_name, email, _source, _raw_metadata in learner_rows:
            try:
                normalized_email = normalize_account_email(email)
            except Exception:
                skipped_invalid_count += 1
                continue

            if not normalized_email:
                skipped_invalid_count += 1
                continue

            if normalized_email in existing_emails:
                skipped_existing_count += 1
                continue

            normalized_full_name = str(full_name or "").strip()
            generated_username = build_unique_support_account_username(
                email=normalized_email,
                full_name=normalized_full_name,
                existing_usernames=existing_usernames,
            )
            account_metadata = {
                "synced_from_learners": True,
                "provisioned_by": "sync_learners_to_support_accounts",
                "session_active": False,
                "console_status": "Off",
            }
            prepared_rows.append(
                [
                    generated_username,
                    normalized_full_name or generated_username,
                    normalized_email,
                    ACCOUNT_SCOPE_REQUESTER,
                    ROLE_USER,
                    True,
                    json.dumps(account_metadata),
                ]
            )
            existing_emails.add(normalized_email)
            inserted_count += 1

        if not dry_run:
            atomic_context = transaction.atomic() if hasattr(transaction, "atomic") else nullcontext()
            with atomic_context:
                with connection.cursor() as cursor:
                    for row in prepared_rows:
                        cursor.execute(
                            """
                            INSERT INTO support_accounts (
                              username,
                              full_name,
                              email,
                              account_scope,
                              role,
                              is_active,
                              metadata
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                            """,
                            row,
                        )
                    cursor.execute(
                        """
                        UPDATE learners AS l
                        SET support_account_id = sa.id,
                            updated_at = NOW()
                        FROM support_accounts AS sa
                        WHERE LOWER(TRIM(l.email)) = LOWER(TRIM(sa.email))
                          AND sa.account_scope = %s
                          AND (l.support_account_id IS NULL OR l.support_account_id <> sa.id)
                        """,
                        [ACCOUNT_SCOPE_REQUESTER],
                    )
                    linked_count = cursor.rowcount

        summary_prefix = "Prepared" if dry_run else "Synced"
        self.stdout.write(
            self.style.SUCCESS(
                f"{summary_prefix} {inserted_count} learner account(s) into support_accounts. "
                f"Linked {linked_count} learner profile(s). "
                f"Skipped {skipped_existing_count} existing email(s) and {skipped_invalid_count} invalid email(s)."
            )
        )
