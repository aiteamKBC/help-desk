from django.core.management.base import BaseCommand

from support_portal.services import sync_auto_managed_ticket_sla_statuses


class Command(BaseCommand):
    help = "Recalculate SLA status for auto-managed tickets and persist any changes."

    def handle(self, *args, **options):
        result = sync_auto_managed_ticket_sla_statuses()
        self.stdout.write(
            self.style.SUCCESS(
                "SLA sync completed. "
                f"Scanned {result['scanned']} ticket(s), "
                f"updated {result['updated']}, "
                f"breached {result['breached']}, "
                f"attention required {result['attentionRequired']}."
            )
        )
