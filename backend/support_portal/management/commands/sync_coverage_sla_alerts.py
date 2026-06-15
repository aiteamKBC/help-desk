from django.core.management.base import BaseCommand

from support_portal.services import sync_coverage_ticket_sla_alerts


class Command(BaseCommand):
    help = "Recalculate coverage session SLA alerts and notify the configured webhook."

    def handle(self, *args, **options):
        result = sync_coverage_ticket_sla_alerts()
        self.stdout.write(
            self.style.SUCCESS(
                "Coverage SLA sync completed. "
                f"Scanned {result['scanned']} ticket(s), "
                f"updated {result['updated']}, "
                f"warnings {result['warnings']}, "
                f"escalations {result['escalations']}, "
                f"breached {result['breached']}, "
                f"attention required {result['attentionRequired']}."
            )
        )
