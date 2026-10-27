"""Regression tests for public support hardening; all external services are mocked."""
from unittest.mock import MagicMock, patch

from django.db.utils import OperationalError as DjangoOperationalError
from django.test import RequestFactory, SimpleTestCase, override_settings

from support_portal import chatbot, services, views
from support_portal.roles import ROLE_TUTOR
from support_portal.services import SUPPORT_NOTIFICATION_RETRY_BACKOFF_SECONDS


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


class EscalationDoubleClickTests(SimpleTestCase):
    """A learner who taps the button twice must end up with one ticket."""

    def test_concurrent_escalations_for_one_learner_create_a_single_ticket(self):
        import threading

        requester = {"display_name": "Aya", "learner": {"id": 4242}}
        created: list[str] = []
        started = threading.Barrier(2)

        def find_existing(learner_id):
            # The second caller must not look until the first has finished, or
            # this test would pass only by luck of the scheduler.
            return {"public_id": created[0], "status": "Open"} if created else None

        def create(payload, **kwargs):
            created.append("KBC-000999")
            return {"ticket": {"id": "KBC-000999", "status": "Open"}}

        outcomes: list[dict] = []

        def escalate():
            started.wait()
            outcomes.append(chatbot._escalate_to_ticket(requester, "aya@example.com", "lms", [], "it failed"))

        with (
            patch.object(services, "find_latest_active_ticket_for_learner", side_effect=find_existing),
            patch.object(services, "create_ticket", side_effect=create) as create_mock,
        ):
            threads = [threading.Thread(target=escalate) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertEqual(create_mock.call_count, 1)
        self.assertEqual([outcome["id"] for outcome in outcomes], ["KBC-000999", "KBC-000999"])
        self.assertEqual(sorted(outcome["created"] for outcome in outcomes), [False, True])


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
        sleep.assert_called_once_with(SUPPORT_NOTIFICATION_RETRY_BACKOFF_SECONDS[0])

    def test_does_not_retry_a_timeout(self):
        """A timeout is the one failure that may already have been processed.

        n8n could have sent the email and lost the reply, so sending again risks
        a duplicate. Silence is preferred here and nowhere else.
        """
        with (
            patch.object(services, "get_support_notification_webhook_url", return_value="https://example.test/webhook"),
            patch.object(services, "post_json_webhook",
                         return_value=(True, False, None, {"message": "Request timed out."})) as deliver,
        ):
            result = services.send_support_notification_webhook({"event": "quick_ticket_submitted"})
        self.assertFalse(result["delivered"])
        self.assertEqual(result["attempts"], 1)
        deliver.assert_called_once()

    def test_retries_a_connection_failure_that_never_reached_the_webhook(self):
        """Refused, DNS and TLS failures never arrive, so a retry cannot duplicate.

        This is the case that lost KBC-000808: one attempt, a transport failure,
        and the support team never heard the ticket had been opened.
        """
        with (
            patch.object(services, "get_support_notification_webhook_url", return_value="https://example.test/webhook"),
            patch.object(services, "post_json_webhook", side_effect=[
                (True, False, None, None),
                (True, False, None, None),
                (True, True, 200, {"ok": True}),
            ]) as deliver,
            patch.object(services.time, "sleep"),
        ):
            result = services.send_support_notification_webhook({"event": "ticket_created"})
        self.assertTrue(result["delivered"])
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(deliver.call_count, 3)

    def test_gives_up_after_the_attempt_limit(self):
        with (
            patch.object(services, "get_support_notification_webhook_url", return_value="https://example.test/webhook"),
            patch.object(services, "post_json_webhook", return_value=(True, False, None, None)) as deliver,
            patch.object(services.time, "sleep"),
        ):
            result = services.send_support_notification_webhook({"event": "ticket_created"})
        self.assertFalse(result["delivered"])
        self.assertEqual(result["attempts"], services.SUPPORT_NOTIFICATION_MAX_ATTEMPTS)
        self.assertEqual(deliver.call_count, services.SUPPORT_NOTIFICATION_MAX_ATTEMPTS)

    def test_a_client_error_is_never_retried(self):
        with (
            patch.object(services, "get_support_notification_webhook_url", return_value="https://example.test/webhook"),
            patch.object(services, "post_json_webhook", return_value=(True, False, 404, None)) as deliver,
        ):
            result = services.send_support_notification_webhook({"event": "ticket_created"})
        self.assertEqual(result["attempts"], 1)
        deliver.assert_called_once()


class TicketCreatedNotificationGuardTests(SimpleTestCase):
    def test_does_not_send_the_opening_mail_twice(self):
        notified = {"metadata": {services.TICKET_CREATED_NOTIFICATION_SENT_AT_METADATA_KEY: "2026-10-16T00:00:00Z"}}
        self.assertFalse(services.should_notify_ticket_created(notified))
        self.assertTrue(services.should_notify_ticket_created({"metadata": {}}))
        self.assertTrue(services.should_notify_ticket_created({}))

    def test_queueing_is_skipped_for_an_already_notified_ticket(self):
        ticket = {
            "id": 1,
            "public_id": "KBC-000001",
            "metadata": {services.TICKET_CREATED_NOTIFICATION_SENT_AT_METADATA_KEY: "2026-10-16T00:00:00Z"},
        }
        with patch.object(services, "queue_support_notification_delivery") as queue:
            services.queue_ticket_created_notification(ticket)
        queue.assert_not_called()


@override_settings(SUPPORT_SSO_SECRET="test-sso-secret", SUPPORT_SSO_TOKEN_MAX_AGE_SECONDS=300)
class SsoTokenLifetimeTests(SimpleTestCase):
    """A token must not be able to disable the check on its own lifetime."""

    @staticmethod
    def _mint(payload):
        import base64
        import hashlib
        import hmac
        import json as json_module

        from django.conf import settings

        def segment(raw: bytes) -> str:
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

        body = segment(json_module.dumps(payload, separators=(",", ":")).encode())
        signature = hmac.new(settings.SUPPORT_SSO_SECRET.encode(), body.encode(), hashlib.sha256).digest()
        return f"{body}.{segment(signature)}"

    def test_accepts_a_token_within_its_allowed_lifetime(self):
        import time as time_module

        now = int(time_module.time())
        token = self._mint({"email": "aya@example.com", "iat": now, "exp": now + 300})
        self.assertEqual(services.verify_support_sso_token(token), "aya@example.com")

    def test_rejects_a_long_lived_token_that_omits_its_issue_time(self):
        import time as time_module

        now = int(time_module.time())
        token = self._mint({"email": "aya@example.com", "exp": now + 365 * 24 * 3600})
        with self.assertRaises(services.ApiError) as error:
            services.verify_support_sso_token(token)
        self.assertEqual(error.exception.status_code, 401)

    def test_rejects_a_long_lived_token_that_declares_its_issue_time(self):
        import time as time_module

        now = int(time_module.time())
        token = self._mint({"email": "aya@example.com", "iat": now, "exp": now + 365 * 24 * 3600})
        with self.assertRaises(services.ApiError) as error:
            services.verify_support_sso_token(token)
        self.assertEqual(error.exception.status_code, 401)
