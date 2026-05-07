from django.core.management.base import BaseCommand
from django.db import connection

from support_portal.services import (
    STATUS_REASON_AWAITING_MEETING,
    STATUS_REASON_CLOSING_BY_CHATBOT,
)


STATUS_REASON_CLOSED_DUE_TO_INACTIVITY = "Closed due to inactivity"


class Command(BaseCommand):
    help = "Normalize legacy ticket status_reason values to the current English labels."

    def handle(self, *args, **options):
        replacements = [
            ("awating meeting", STATUS_REASON_AWAITING_MEETING),
            ("closing by chat bot", STATUS_REASON_CLOSING_BY_CHATBOT),
            ("اتقفلت عشان الوقت", STATUS_REASON_CLOSED_DUE_TO_INACTIVITY),
        ]

        updated_rows = 0

        with connection.cursor() as cursor:
            for old_value, new_value in replacements:
                cursor.execute(
                    """
                    UPDATE tickets
                    SET status_reason = %s,
                        updated_at = NOW()
                    WHERE status_reason = %s
                    """,
                    [new_value, old_value],
                )
                updated_rows += cursor.rowcount

        self.stdout.write(
            self.style.SUCCESS(f"Normalized {updated_rows} ticket status reason value(s).")
        )
