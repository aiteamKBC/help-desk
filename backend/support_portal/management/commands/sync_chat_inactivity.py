from django.core.management.base import BaseCommand

from support_portal.services import sync_open_ticket_inactivity


class Command(BaseCommand):
    help = "Send inactivity reminders and auto-close expired open chats."

    def add_arguments(self, parser):
        parser.add_argument(
            "--ticket",
            dest="public_id",
            help="Limit the inactivity sweep to a single ticket public id.",
        )

    def handle(self, *args, **options):
        result = sync_open_ticket_inactivity(public_id=options.get("public_id"))
        self.stdout.write(
            self.style.SUCCESS(
                "Chat inactivity sync completed. "
                f"Scanned {result['scanned']} open ticket(s), "
                f"sent {result['reminded']} reminder(s), "
                f"closed {result['closed']} chat(s)."
            )
        )
