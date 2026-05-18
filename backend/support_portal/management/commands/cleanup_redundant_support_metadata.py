from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection, transaction


class Command(BaseCommand):
    help = "Remove redundant relationship metadata now covered by explicit foreign keys."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many rows would be cleaned without updating the database.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM support_accounts
                WHERE metadata ? 'linked_learner_id'
                   OR metadata ? 'linked_learner_source'
                   OR metadata ? 'learner_metadata_snapshot'
                """
            )
            support_account_rows = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM learners
                WHERE metadata ? 'linked_account_id'
                   OR metadata ? 'linked_account_username'
                """
            )
            learner_rows = cursor.fetchone()[0]

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Would clean {support_account_rows} support account row(s) and {learner_rows} learner row(s)."
                )
            )
            return

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE support_accounts
                    SET metadata = COALESCE(metadata, '{}'::jsonb)
                        - 'linked_learner_id'
                        - 'linked_learner_source'
                        - 'learner_metadata_snapshot',
                        updated_at = NOW()
                    WHERE metadata ? 'linked_learner_id'
                       OR metadata ? 'linked_learner_source'
                       OR metadata ? 'learner_metadata_snapshot'
                    """
                )
                cleaned_support_accounts = cursor.rowcount

                cursor.execute(
                    """
                    UPDATE learners
                    SET metadata = COALESCE(metadata, '{}'::jsonb)
                        - 'linked_account_id'
                        - 'linked_account_username',
                        updated_at = NOW()
                    WHERE metadata ? 'linked_account_id'
                       OR metadata ? 'linked_account_username'
                    """
                )
                cleaned_learners = cursor.rowcount

        self.stdout.write(
            self.style.SUCCESS(
                f"Cleaned {cleaned_support_accounts} support account row(s) and {cleaned_learners} learner row(s)."
            )
        )
