from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from io import StringIO
from django.core.management import call_command
from django.test import SimpleTestCase
from unittest.mock import patch
from zoneinfo import ZoneInfo

from support_portal import services


class LearnerLookupTests(SimpleTestCase):
    def test_find_learner_by_email_returns_local_match_without_legacy_lookup(self):
        learner = {"id": 7, "full_name": "Local Learner", "email": "local@example.com", "phone": None}

        with (
            patch.object(services, "fetch_local_learner_by_email", return_value=learner) as fetch_local,
            patch.object(services, "fetch_legacy_learner_by_email") as fetch_legacy,
        ):
            result = services.find_learner_by_email("local@example.com")

        self.assertEqual(result, learner)
        fetch_local.assert_called_once_with("local@example.com")
        fetch_legacy.assert_not_called()

    def test_find_learner_by_email_syncs_legacy_match_on_local_miss(self):
        legacy_learner = {
            "external_learner_id": "123",
            "full_name": "Legacy Learner",
            "email": "legacy@example.com",
            "phone": "01000000000",
        }
        synced_learner = {"id": 8, **legacy_learner}

        with (
            patch.object(services, "fetch_local_learner_by_email", return_value=None),
            patch.object(services, "fetch_legacy_learner_by_email", return_value=legacy_learner) as fetch_legacy,
            patch.object(services, "upsert_learner_record", return_value=synced_learner) as upsert_learner,
        ):
            result = services.find_learner_by_email("legacy@example.com")

        self.assertEqual(result, synced_learner)
        fetch_legacy.assert_called_once_with("legacy@example.com")
        upsert_learner.assert_called_once_with(
            legacy_learner,
            source="legacy_kbc_users_data",
            metadata={"legacy_source": "kbc_users_data", "synced_on_demand": True},
        )

    def test_verify_email_response_uses_synced_learner(self):
        learner = {"id": 9, "full_name": "Synced Learner", "email": "synced@example.com"}

        with patch.object(services, "find_learner_by_email", return_value=learner) as find_learner:
            response = services.get_verify_email_response({"email": "SYNCED@EXAMPLE.COM"})

        self.assertEqual(
            response,
            {
                "exists": True,
                "learner": {
                    "id": 9,
                    "fullName": "Synced Learner",
                    "email": "synced@example.com",
                },
                "message": "Email verified.",
            },
        )
        find_learner.assert_called_once_with("synced@example.com")


class SupportSessionValidationTests(SimpleTestCase):
    def test_support_session_window_accepts_uk_hours_until_four_pm(self):
        requested_datetime = datetime(2026, 5, 10, 15, 0, tzinfo=ZoneInfo("Europe/London"))

        self.assertTrue(services.is_within_support_session_window(requested_datetime))

    def test_support_session_window_rejects_after_four_pm_uk_time(self):
        requested_datetime = datetime(2026, 5, 10, 16, 30, tzinfo=ZoneInfo("Europe/London"))

        self.assertFalse(services.is_within_support_session_window(requested_datetime))

    def test_extract_booking_webhook_result_marks_teams_reservation_as_confirmed(self):
        result = services.extract_booking_webhook_result(
            {
                "eventId": "evt_123",
                "joinUrl": "https://teams.microsoft.com/l/meetup-join/example",
                "organizerEmail": "support@example.com",
            },
            delivered=True,
            status=201,
        )

        self.assertTrue(result["reservationConfirmed"])
        self.assertEqual(result["calendarEventId"], "evt_123")
        self.assertEqual(result["meetingJoinUrl"], "https://teams.microsoft.com/l/meetup-join/example")

    def test_extract_booking_webhook_result_marks_conflict_as_unavailable(self):
        result = services.extract_booking_webhook_result(
            {"available": False, "message": "This slot is already booked."},
            delivered=False,
            status=409,
        )

        self.assertFalse(result["reservationConfirmed"])
        self.assertTrue(result["slotUnavailable"])
        self.assertEqual(result["message"], "This slot is already booked.")


class SlaPolicyTests(SimpleTestCase):
    def test_open_ticket_keeps_pending_review(self):
        sla_status, attention_required, attention_reason = services.derive_sla_state(
            "Open",
            datetime.now(timezone.utc),
            "Breached",
        )

        self.assertEqual(sla_status, "Pending Review")
        self.assertFalse(attention_required)
        self.assertIsNone(attention_reason)

    def test_closed_ticket_becomes_on_track(self):
        sla_status, attention_required, attention_reason = services.derive_sla_state(
            "Closed",
            datetime.now(timezone.utc),
            "Pending Review",
        )

        self.assertEqual(sla_status, "On Track")
        self.assertFalse(attention_required)
        self.assertIsNone(attention_reason)

    def test_pending_ticket_within_three_days_is_on_track(self):
        created_at = datetime.now(timezone.utc) - timedelta(days=2, hours=23)

        sla_status, attention_required, attention_reason = services.derive_sla_state(
            "Pending",
            created_at,
            "Pending Review",
        )

        self.assertEqual(sla_status, "On Track")
        self.assertFalse(attention_required)
        self.assertIsNone(attention_reason)

    def test_pending_ticket_after_three_days_is_breached_and_flagged(self):
        created_at = datetime.now(timezone.utc) - timedelta(days=3, minutes=1)

        sla_status, attention_required, attention_reason = services.derive_sla_state(
            "Pending",
            created_at,
            "Pending Review",
        )

        self.assertEqual(sla_status, "Breached")
        self.assertTrue(attention_required)
        self.assertEqual(attention_reason, services.SLA_ATTENTION_REASON_PENDING_OVERDUE)

    def test_to_sender_label_accepts_string_metadata_payload(self):
        label = services.to_sender_label("assistant", '{"original_sender":"bot"}')

        self.assertEqual(label, "Bot")

    def test_sync_auto_managed_ticket_sla_statuses_counts_updates_and_breaches(self):
        tickets = [
            {
                "id": 1,
                "status": "Pending",
                "sla_status": "On Track",
                "metadata": {"sla_attention_required": False},
                "created_at": datetime.now(timezone.utc) - timedelta(days=4),
            },
            {
                "id": 2,
                "status": "Open",
                "sla_status": "Pending Review",
                "metadata": {"sla_attention_required": False},
                "created_at": datetime.now(timezone.utc),
            },
        ]

        synced_tickets = [
            {
                **tickets[0],
                "sla_status": "Breached",
                "metadata": {"sla_attention_required": True, "sla_attention_reason": services.SLA_ATTENTION_REASON_PENDING_OVERDUE},
            },
            {
                **tickets[1],
                "sla_status": "Pending Review",
                "metadata": {"sla_attention_required": False},
            },
        ]

        with (
            patch.object(services, "run_query", return_value=tickets) as run_query,
            patch.object(services, "apply_ticket_sla_policy", side_effect=synced_tickets) as apply_ticket_sla_policy,
        ):
            result = services.sync_auto_managed_ticket_sla_statuses()

        self.assertEqual(result, {"scanned": 2, "updated": 1, "breached": 1, "attentionRequired": 1})
        run_query.assert_called_once()
        self.assertEqual(apply_ticket_sla_policy.call_count, 2)

    def test_serialize_ticket_summary_marks_chat_active_only_when_conversation_is_active(self):
        ticket_row = {
            "public_id": "KBC-000123",
            "learner_name": "Ali Test",
            "learner_email": "ali@example.com",
            "learner_phone": "01000000000",
            "category": "Learning",
            "technical_subcategory": "",
            "inquiry": "Need help",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_username": None,
            "assigned_team": "Unassigned",
            "conversation_id": 12,
            "conversation_status": "open",
            "conversation_metadata": {"is_active_conversation": True, "live_chat_requested": True},
            "last_message_at": None,
            "sla_status": "Pending Review",
            "evidence_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "metadata": {},
        }

        summary = services.serialize_ticket_summary(ticket_row)
        inactive_summary = services.serialize_ticket_summary({**ticket_row, "conversation_metadata": {}})

        self.assertTrue(summary["chatIsActive"])
        self.assertTrue(summary["liveChatRequested"])
        self.assertFalse(inactive_summary["chatIsActive"])
        self.assertFalse(inactive_summary["liveChatRequested"])


class SlaSyncCommandTests(SimpleTestCase):
    def test_sync_ticket_sla_statuses_command_reports_summary(self):
        output = StringIO()

        with patch(
            "support_portal.management.commands.sync_ticket_sla_statuses.sync_auto_managed_ticket_sla_statuses",
            return_value={"scanned": 7, "updated": 3, "breached": 2, "attentionRequired": 2},
        ) as sync_auto_managed_ticket_sla_statuses:
            call_command("sync_ticket_sla_statuses", stdout=output)

        self.assertIn("SLA sync completed. Scanned 7 ticket(s), updated 3, breached 2, attention required 2.", output.getvalue())
        sync_auto_managed_ticket_sla_statuses.assert_called_once_with()


class AdminTicketUpdateTests(SimpleTestCase):
    def test_update_admin_ticket_requires_note_when_status_changes(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "assigned_team": "Unassigned",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "assigned_agent_username": None,
            "assigned_agent_name": None,
        }

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.update_admin_ticket("KBC-000017", {"status": "Closed", "note": ""})

        self.assertEqual(error_context.exception.status_code, 400)
        self.assertEqual(error_context.exception.message, "Add an internal note before changing the ticket status.")

    def test_update_admin_ticket_rejects_invalid_status_reason_for_pending(self):
        ticket = {
            "id": 17,
            "public_id": "KBC-000017",
            "status": "Open",
            "status_reason": "",
            "assigned_agent_id": None,
            "assigned_team": "Unassigned",
            "sla_status": "Pending Review",
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "closed_at": None,
            "conversation_id": None,
            "conversation_metadata": {},
            "assigned_agent_username": None,
            "assigned_agent_name": None,
            "inquiry": "Help needed",
        }

        with (
            patch.object(services.transaction, "atomic", return_value=nullcontext()),
            patch.object(services, "run_query_one", return_value=ticket),
            patch.object(services, "apply_ticket_sla_policy"),
        ):
            with self.assertRaises(services.ApiError) as error_context:
                services.update_admin_ticket(
                    "KBC-000017",
                    {"status": "Pending", "statusReason": "Closed via Agent", "note": "Triage update"},
                )

        self.assertEqual(error_context.exception.status_code, 400)
        self.assertEqual(error_context.exception.message, "Invalid status reason for pending tickets.")


class BookingContextTests(SimpleTestCase):
    def test_build_public_chat_id_prefers_ticket_public_id(self):
        self.assertEqual(services.build_public_chat_id("KBC-000123", 77), "KBC-000123")

    def test_build_public_chat_id_prefers_conversation_metadata_value(self):
        self.assertEqual(
            services.build_public_chat_id("KBC-000123", 77, {"chat_public_id": "CHAT-KBC-ROOT"}),
            "CHAT-KBC-ROOT",
        )

    def test_get_support_booking_url_returns_configured_value(self):
        with patch.object(services.settings, "SUPPORT_BOOKING_URL", "https://outlook.office.com/book/example"):
            response = services.get_support_booking_url()

        self.assertEqual(response, "https://outlook.office.com/book/example")

    def test_get_ticket_booking_context_response_returns_prefill_payload(self):
        ticket_row = {
            "public_id": "KBC-000123",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "inquiry": "Need help joining my live class.",
            "status": "Open",
            "learner_id": 11,
            "learner_full_name": "Ali Test",
            "learner_email": "ali@example.com",
            "learner_phone": "01000000000",
        }

        with (
            patch.object(services, "run_query_one", return_value=ticket_row) as run_query_one,
            patch.object(services.settings, "SUPPORT_BOOKING_URL", "https://outlook.office.com/book/example"),
        ):
            response = services.get_ticket_booking_context_response("KBC-000123")

        self.assertEqual(response["bookingUrl"], "https://outlook.office.com/book/example")
        self.assertFalse(response["externalAutofillSupported"])
        self.assertEqual(response["learner"]["fullName"], "Ali Test")
        self.assertEqual(response["prefill"]["email"], "ali@example.com")
        self.assertEqual(response["prefill"]["specialRequests"], "Need help joining my live class.")
        run_query_one.assert_called_once()

    def test_get_ticket_chat_context_response_returns_intro_message(self):
        ticket_row = {
            "public_id": "KBC-000123",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "learner_id": 11,
            "learner_full_name": "Ali Test",
            "learner_email": "ali@example.com",
        }

        with patch.object(services, "run_query_one", return_value=ticket_row) as run_query_one:
            response = services.get_ticket_chat_context_response("KBC-000123")

        self.assertEqual(
            response["introMessage"],
            "Hello Ali Test, Thank you for reaching Kent College Support, I understand you are reaching us for an issue related to Teams, am I correct?",
        )
        self.assertEqual(response["learner"]["fullName"], "Ali Test")
        self.assertEqual(response["ticket"]["category"], "Technical")
        self.assertEqual(response["ticket"]["technicalSubcategory"], "Teams")
        run_query_one.assert_called_once()

    def test_get_ticket_chat_history_response_keeps_intro_message_when_not_persisted_yet(self):
        ticket_row = {
            "id": 1,
            "public_id": "KBC-000123",
            "category": "Technical",
            "technical_subcategory": "Teams",
            "status": "Open",
            "status_reason": "",
            "assigned_team": "Unassigned",
            "sla_status": "Pending Review",
            "created_at": datetime(2026, 5, 7, 10, 0, tzinfo=timezone.utc),
            "metadata": {},
            "conversation_id": 55,
            "conversation_metadata": {},
            "learner_name": "Ali Test",
        }

        with (
            patch.object(services, "run_query_one", return_value=ticket_row),
            patch.object(services, "run_query", return_value=[]),
        ):
            response = services.get_ticket_chat_history_response("KBC-000123")

        self.assertEqual(len(response["chatHistory"]), 1)
        self.assertEqual(response["chatHistory"][0]["sender"], "bot")
        self.assertIn("Hello Ali Test", response["chatHistory"][0]["text"])
