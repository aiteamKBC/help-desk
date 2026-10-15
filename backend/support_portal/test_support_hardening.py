"""Regression tests for public support hardening; all external services are mocked."""
from unittest.mock import MagicMock, patch

from django.db.utils import OperationalError as DjangoOperationalError
from django.test import RequestFactory, SimpleTestCase

from support_portal import chatbot, services, views
from support_portal.roles import ROLE_TUTOR


class PublicAssistantHardeningTests(SimpleTestCase):
    def test_public_assistant_rejects_staff_mode_before_identity_lookup(self):
        with patch.object(chatbot, "_resolve_assistant_requester") as lookup:
            with self.assertRaises(services.ApiError) as error:
                chatbot.get_support_assistant_response({"message": "internal notes", "mode": "staff"})
        self.assertEqual(error.exception.status_code, 403)
        lookup.assert_not_called()

    def test_public_assistant_uses_server_resolved_tutor_role_not_request_mode(self):
        requester = {"display_name": "Tutor", "role": "tutor", "learner": {"id": 3}}
        result = {"reply": "Open My Teaching.", "route": "lms", "escalate": False, "links": [], "kbDistance": .2}
        with (
            patch.object(chatbot, "_resolve_assistant_requester", return_value=("tutor@example.com", requester)),
            patch.object(chatbot, "generate_assistant_reply", return_value=result) as reply,
            patch.object(chatbot, "log_assistant_turn"),
        ):
            chatbot.get_support_assistant_response({"message": "Help", "mode": "learner", "sessionId": "safe"})
        self.assertEqual(reply.call_args.kwargs["mode"], "tutor")


class RequesterRoleHardeningTests(SimpleTestCase):
    def test_tutor_group_promotes_an_otherwise_learner_account(self):
        with (
            patch.object(services, "has_public_requester_coach_access", return_value=False),
            patch.object(services, "has_public_requester_tutor_access", return_value=True),
        ):
            self.assertEqual(services.apply_public_requester_role_overrides("tutor@example.com", "user"), ROLE_TUTOR)


class HealthEndpointTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_health_confirms_a_real_database_query(self):
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        database = MagicMock()
        database.cursor.return_value = cursor_context
        with patch.object(views, "connection", database):
            response = views.health(self.factory.get("/api/health"))
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), {"ok": True, "databaseReachable": True})
        cursor.execute.assert_called_once_with("SELECT 1")

    def test_health_returns_503_when_database_is_down(self):
        database = MagicMock()
        database.cursor.side_effect = DjangoOperationalError("down")
        with self.assertLogs("support_portal.views", level="WARNING"):
            with patch.object(views, "connection", database):
                response = views.health(self.factory.get("/api/health"))
        self.assertEqual(response.status_code, 503)
        self.assertJSONEqual(response.content.decode(), {"ok": False, "databaseReachable": False})


class NotificationRetryTests(SimpleTestCase):
    def test_retries_explicit_transient_webhook_failure_once(self):
        with (
            patch.object(services, "get_support_notification_webhook_url", return_value="https://example.test/webhook"),
            patch.object(services, "post_json_webhook", side_effect=[
                (True, False, 500, {"message": "retry"}),
                (True, True, 200, {"ok": True}),
            ]) as deliver,
            patch.object(services.time, "sleep") as sleep,
        ):
            result = services.send_support_notification_webhook({
                "event": "quick_ticket_submitted", "ticketId": "KBC-000001", "recipientType": "requester",
            })
        self.assertTrue(result["delivered"])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["deliveryKey"], "quick_ticket_submitted:KBC-000001:requester")
        self.assertEqual(deliver.call_count, 2)
        self.assertEqual(deliver.call_args.kwargs["headers"], {"X-Support-Delivery-Key": result["deliveryKey"]})
        sleep.assert_called_once_with(.25)

    def test_does_not_retry_an_ambiguous_transport_failure(self):
        with (
            patch.object(services, "get_support_notification_webhook_url", return_value="https://example.test/webhook"),
            patch.object(services, "post_json_webhook", return_value=(True, False, None, None)) as deliver,
        ):
            result = services.send_support_notification_webhook({"event": "quick_ticket_submitted"})
        self.assertFalse(result["delivered"])
        self.assertEqual(result["attempts"], 1)
        deliver.assert_called_once()
