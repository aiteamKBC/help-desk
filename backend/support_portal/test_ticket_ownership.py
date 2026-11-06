"""Ownership and resolver attribution without external calls or a live database."""
import json
from contextlib import nullcontext
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from support_portal import services


class TicketOwnershipTests(SimpleTestCase):
    def setUp(self):
        self.ticket = {
            "id": 17, "public_id": "KBC-000017", "status": "Pending",
            "status_reason": "Awaiting resolution", "assigned_agent_id": None,
            "assigned_team": "Support Desk", "sla_status": "On Track",
            "metadata": {}, "created_at": datetime.now(timezone.utc),
            "closed_at": None, "conversation_id": None, "conversation_metadata": {},
            "inquiry": "Help needed", "is_archived": False,
        }
        self.actor = {
            "id": 9, "username": "omar", "full_name": "Omar Helmy",
            "email": "omar@example.com", "role": "agent", "account_scope": "staff",
            "is_active": True, "metadata": {"legacy_support_access": True},
        }
        self.cursor = MagicMock()
        context = MagicMock()
        context.__enter__.return_value = self.cursor
        self.connection = MagicMock()
        self.connection.cursor.return_value = context

    def update(self, payload, *, can_receive=True):
        def get_row(sql, params):
            if "FROM support_accounts" in sql:
                return self.actor
            if "FROM ticket_history" in sql:
                return None
            self.assertIn("FOR UPDATE OF t", sql)
            return self.ticket

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", side_effect=get_row),
            patch.object(services, "fetch_actor_by_username", return_value=self.actor),
            patch.object(services, "require_actor_can_access_admin_ticket"),
            patch.object(services, "account_can_receive_ticket_assignment", return_value=can_receive),
            patch.object(services, "apply_ticket_sla_policy"),
            patch.object(services, "connection", self.connection),
            patch.object(services, "insert_history_event") as history,
            patch.object(services, "fetch_admin_ticket_detail", return_value={"ticket": {"id": "KBC-000017"}}),
            patch.object(services, "queue_quick_ticket_closed_notification"),
        ):
            result = services.update_admin_ticket("KBC-000017", {**payload, "actorUsername": "omar"})
        return result, history

    def test_claim_records_real_account_email_and_time(self):
        _, history = self.update({"claim": True})
        values = next(call.args[1] for call in self.cursor.execute.call_args_list if "UPDATE tickets" in call.args[0])
        self.assertEqual(values[2], 9)
        ownership = json.loads(values[5])["assigned_agent_record"]
        self.assertEqual(ownership["email"], "omar@example.com")
        self.assertEqual(ownership["assignmentSource"], "claim")
        self.assertTrue(ownership["assignedAt"])
        self.assertIn("assignment_changed", [call.args[1] for call in history.call_args_list])

    def test_second_claim_is_rejected_without_writing(self):
        self.ticket["assigned_agent_id"] = 4
        with self.assertRaises(services.ApiError) as error:
            self.update({"claim": True})
        self.assertEqual(error.exception.status_code, 409)
        self.cursor.execute.assert_not_called()

    def test_claim_requires_receiver_access(self):
        with self.assertRaises(services.ApiError) as error:
            self.update({"claim": True}, can_receive=False)
        self.assertEqual(error.exception.status_code, 403)
        self.cursor.execute.assert_not_called()

    def test_closed_ticket_cannot_be_claimed(self):
        self.ticket["status"] = "Closed"
        with self.assertRaises(services.ApiError) as error:
            self.update({"claim": True})
        self.assertEqual(error.exception.status_code, 409)
        self.cursor.execute.assert_not_called()

    def test_closer_is_recorded_separately_from_owner(self):
        self.ticket["assigned_agent_id"] = 4
        self.ticket["assigned_agent_name"] = "Khaled"
        self.ticket["metadata"] = {"assigned_agent_record": {"id": 4, "email": "khaled@example.com", "assignedAt": "2026-11-06T10:00:00Z"}}
        self.update({"status": "Closed", "statusReason": "Closed via Agent", "note": "Resolved"})
        values = next(call.args[1] for call in self.cursor.execute.call_args_list if "UPDATE tickets" in call.args[0])
        metadata = json.loads(values[5])
        self.assertEqual(values[2], 4)
        self.assertEqual(metadata["assigned_agent_record"]["id"], 4)
        self.assertEqual(metadata["resolved_by"]["id"], 9)
        self.assertEqual(metadata["resolved_by"]["email"], "omar@example.com")

    def test_team_transfer_clears_owner_and_preserves_history(self):
        self.ticket["assigned_agent_id"] = 4
        self.ticket["assigned_agent_name"] = "Khaled"
        self.ticket["metadata"] = {"assigned_agent_record": {"id": 4, "email": "khaled@example.com"}}
        self.actor["role"] = "admin"
        with patch.object(services, "normalize_assigned_team", return_value="Ai Team"), patch.object(services, "actor_can_transfer_ticket_between_teams", return_value=True), patch.object(services, "notify_team_members_ticket_assignment"):
            _, history = self.update({"assignedTeam": "Ai Team", "note": "Moved to Ai Team"})
        values = next(call.args[1] for call in self.cursor.execute.call_args_list if "UPDATE tickets" in call.args[0])
        self.assertIsNone(values[2])
        self.assertNotIn("assigned_agent_record", json.loads(values[5]))
        self.assertIn("team_transferred", [call.args[1] for call in history.call_args_list])

    def test_reopening_clears_resolver_but_keeps_owner(self):
        self.ticket["status"] = "Closed"
        self.ticket["assigned_agent_id"] = 4
        self.ticket["metadata"] = {"resolved_by": {"id": 9}, "assigned_agent_record": {"id": 4}}
        self.update({"status": "Open", "note": "Needs further review"})
        values = next(call.args[1] for call in self.cursor.execute.call_args_list if "UPDATE tickets" in call.args[0])
        metadata = json.loads(values[5])
        self.assertNotIn("resolved_by", metadata)
        self.assertEqual(metadata["assigned_agent_record"]["id"], 4)
