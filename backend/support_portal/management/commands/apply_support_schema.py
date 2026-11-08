from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Apply the legacy support SQL schema files (migrations/*.sql, in name order) to the configured database."

    def handle(self, *args, **options):
        migrations_dir = Path(__file__).resolve().parents[3] / "migrations"
        schema_paths = sorted(migrations_dir.glob("[0-9][0-9][0-9]_*.sql"))

        if not schema_paths:
            raise CommandError(f"No schema files found in: {migrations_dir}")

        for schema_path in schema_paths:
            sql = schema_path.read_text(encoding="utf-8")
            with connection.cursor() as cursor:
                cursor.execute(sql)
            self.stdout.write(f"Applied {schema_path.name}")

        self.stdout.write(self.style.SUCCESS("Support schema applied successfully."))
