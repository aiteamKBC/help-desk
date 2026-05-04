from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Apply the legacy support SQL schema to the configured database."

    def handle(self, *args, **options):
        schema_path = Path(__file__).resolve().parents[3] / "migrations" / "001_support_schema.sql"

        if not schema_path.exists():
            raise CommandError(f"Schema file not found: {schema_path}")

        sql = schema_path.read_text(encoding="utf-8")

        with connection.cursor() as cursor:
            cursor.execute(sql)

        self.stdout.write(self.style.SUCCESS("Support schema applied successfully."))
