"""Ticket detail must preserve the fields used to display/filter its list row."""
import re
from datetime import datetime, timezone
from unittest.mock import patch

from django.test import SimpleTestCase

from support_portal import services


class TicketDetailConsistencyTests(SimpleTestCase):
    def test_opening_ticket_preserves_subject_requester_source_and_workflow_fields(self):
        stored_row = {
            "id": 907, "public_id": "KBC-000907", "category": "Technical",
            "technical_subcategory": "AI Team", "subject": "Unique search title",
            "inquiry": "Request details", "status": "Pending", "status_reason": "Quick Ticket",
            "sla_status": "On Track", "priority": "Normal", "metadata": {},
            "learner_name": "Test Learner", "learner_email": "learner@example.com",
            "learner_source": "kbc_users_data", "learner_metadata": {},
            "created_at": datetime(2026, 11, 6, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 11, 6, tzinfo=timezone.utc),
        }

        def select_row(sql, params):
            self.assertEqual(params, ["KBC-000907"])
            # Model projection: a field absent from SELECT cannot reach the serializer.
            projection = sql.split("FROM tickets t", 1)[0]
            for field in ("ticket_type", "workflow_stage", "queue_scope", "dashboard_bucket",
                          "can_show_conversation", "can_receive_chat", "resolution_reason",
                          "submitted_for_learner_id"):
                self.assertIn(f"t.{field}", projection)
            return {
                key: value for key, value in stored_row.items()
                if re.search(rf"\b{key}\b", projection)
            }

        with (
            patch.object(services, "run_query_one", side_effect=select_row),
            patch.object(services, "run_query", return_value=[]),
            patch.object(services, "synchronize_coverage_tutor_workflow_ticket", side_effect=lambda row: row),
            patch.object(services, "apply_ticket_sla_policy"),
        ):
            detail = services.fetch_admin_ticket_detail("KBC-000907")

        summary = services.serialize_ticket_summary(stored_row)
        for field in ("subject", "requesterRole", "requesterSource", "createdAt", "status", "ticketState"):
            self.assertEqual(detail["ticket"][field], summary[field], field)
        self.assertEqual(detail["ticket"]["requesterSource"], "kbc_users_data")
        self.assertEqual(detail["ticket"]["subject"], "Unique search title")
