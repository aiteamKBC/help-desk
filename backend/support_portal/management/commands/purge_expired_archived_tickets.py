import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from support_portal import services


class Command(BaseCommand):
    help = (
        "Archived-ticket retention: archived tickets are deleted 3 calendar months after "
        "their archived_at timestamp. Runs as a dry run (report only) unless --execute is "
        "given AND ARCHIVED_TICKET_RETENTION_PURGE_ENABLED=true. Schedule it with cron, e.g. "
        "daily: python manage.py purge_expired_archived_tickets --execute"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Permanently delete eligible tickets. Without it nothing is deleted.",
        )
        parser.add_argument("--batch-size", type=int, default=50)
        parser.add_argument("--max-batches", type=int, default=20)

    def handle(self, *args, **options):
        execute = bool(options["execute"])
        if execute and not getattr(settings, "ARCHIVED_TICKET_RETENTION_PURGE_ENABLED", False):
            raise CommandError(
                "Retention deletion is disabled. Set ARCHIVED_TICKET_RETENTION_PURGE_ENABLED=true "
                "only after the retention policy and schema are approved for this environment."
            )

        try:
            report = services.purge_expired_archived_tickets(
                batch_size=options["batch_size"],
                max_batches=options["max_batches"],
                execute=execute,
            )
        except services.ApiError as error:
            raise CommandError(error.message) from error

        summary = {
            "mode": "execute" if execute else "dry-run",
            "now": report["now"],
            "eligible": len(report["eligible"]),
            "deleted": len(report["deleted"]),
            "skipped": len(report["skipped"]),
            "failed": len(report["failed"]),
            "legacyMissingArchivedAt": len(report["legacyMissingArchivedAt"]),
        }
        self.stdout.write(json.dumps(summary))
        # Ticket ids and dates only: no learner or message content.
        for item in report["eligible"]:
            self.stdout.write(f"eligible {item['ticketId']} archived {item['archivedAt']} delete-after {item['scheduledDeletionAt']}")
        for item in report["failed"]:
            self.stdout.write(self.style.ERROR(f"failed {item.get('ticketId')} {item.get('detail', '')}"))
        if report["legacyMissingArchivedAt"]:
            self.stdout.write(self.style.WARNING(
                "Archived without archived_at (never deleted automatically; needs reconciliation): "
                + ", ".join(report["legacyMissingArchivedAt"])
            ))
