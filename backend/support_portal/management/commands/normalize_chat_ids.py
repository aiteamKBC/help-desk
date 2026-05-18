import json

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from support_portal import services


class Command(BaseCommand):
    help = "Normalize legacy chat identifiers so stored records use CHAT-xxxxxx values."

    def handle(self, *args, **options):
        updated_conversations = 0
        updated_tickets = 0
        updated_history_rows = 0

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, customer_id, metadata
                    FROM conversations
                    ORDER BY id ASC
                    """
                )
                conversations = services.dictfetchall(cursor)

            for conversation in conversations:
                metadata = services.normalize_json_object(conversation.get("metadata"))
                normalized_chat_id = services.build_public_chat_id(
                    metadata.get("ticket_public_id") or conversation.get("customer_id"),
                    conversation.get("id"),
                    metadata,
                )

                if not normalized_chat_id or services.sanitize_text(metadata.get("chat_public_id")) == normalized_chat_id:
                    continue

                metadata["chat_public_id"] = normalized_chat_id
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE conversations
                        SET metadata = %s::jsonb
                        WHERE id = %s
                        """,
                        [json.dumps(metadata), conversation["id"]],
                    )
                updated_conversations += 1

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                      t.id,
                      t.public_id,
                      t.inquiry,
                      t.metadata,
                      t.conversation_id,
                      c.metadata AS conversation_metadata
                    FROM tickets t
                    LEFT JOIN conversations c
                      ON c.id = t.conversation_id
                    ORDER BY t.id ASC
                    """
                )
                tickets = services.dictfetchall(cursor)

            for ticket in tickets:
                normalized_chat_id = services.build_public_chat_id(
                    ticket.get("public_id"),
                    ticket.get("conversation_id"),
                    ticket.get("conversation_metadata"),
                )
                if not normalized_chat_id:
                    continue

                metadata = services.normalize_json_object(ticket.get("metadata"))
                next_metadata = dict(metadata)
                changed = False

                if services.sanitize_text(next_metadata.get("chat_public_id")) != normalized_chat_id:
                    next_metadata["chat_public_id"] = normalized_chat_id
                    changed = True

                admin_documentation = next_metadata.get("admin_documentation")
                if isinstance(admin_documentation, dict):
                    normalized_documentation = services.normalize_admin_documentation(
                        admin_documentation,
                        fallback_inquiry=services.sanitize_text(ticket.get("inquiry")),
                        fallback_chat_id=normalized_chat_id,
                        fallback_ticket_id=services.sanitize_text(ticket.get("public_id")),
                    )
                    if normalized_documentation != admin_documentation:
                        next_metadata["admin_documentation"] = normalized_documentation
                        changed = True

                if not changed:
                    continue

                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE tickets
                        SET metadata = %s::jsonb,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        [json.dumps(next_metadata), ticket["id"]],
                    )
                updated_tickets += 1

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                      h.id,
                      h.payload,
                      t.public_id,
                      t.conversation_id,
                      c.metadata AS conversation_metadata
                    FROM ticket_history h
                    JOIN tickets t
                      ON t.id = h.ticket_id
                    LEFT JOIN conversations c
                      ON c.id = t.conversation_id
                    ORDER BY h.id ASC
                    """
                )
                history_rows = services.dictfetchall(cursor)

            for history_row in history_rows:
                normalized_payload = services.normalize_history_payload(
                    history_row.get("payload"),
                    ticket_public_id=history_row.get("public_id"),
                    conversation_id=history_row.get("conversation_id"),
                    conversation_metadata=history_row.get("conversation_metadata"),
                )
                current_payload = services.normalize_json_object(history_row.get("payload"))
                if normalized_payload == current_payload:
                    continue

                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE ticket_history
                        SET payload = %s::jsonb
                        WHERE id = %s
                        """,
                        [json.dumps(normalized_payload), history_row["id"]],
                    )
                updated_history_rows += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Normalized chat IDs for "
                f"{updated_conversations} conversation(s), "
                f"{updated_tickets} ticket metadata record(s), and "
                f"{updated_history_rows} history event(s)."
            )
        )
