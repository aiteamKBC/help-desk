"""Regressions for native LMS support combined with dynamic team workflows."""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from support_portal import services


class CombinedNotificationTests(SimpleTestCase):
    @override_settings(SUPPORT_OPERATIONS_NOTIFICATION_EMAILS="support@example.com")
    def test_notification_recipients_match_each_workflow(self):
        ticket = {
            "public_id": "KBC-000024",
            "learner_email": "learner@example.com",
            "inquiry": "Please review my evidence.",
            "metadata": {
                services.AI_TEAM_REQUEST_METADATA_KEY: {
                    "personName": "AI Reviewer",
                    "personEmail": "reviewer@example.com",
                },
            },
        }
        for event, recipient_type, recipients in (
            (services.SUPPORT_NOTIFICATION_EVENT_TICKET_CREATED, "operations", ["support@example.com"]),
            (services.SUPPORT_NOTIFICATION_EVENT_QUICK_TICKET_SUBMITTED, "requester", ["learner@example.com"]),
            (services.SUPPORT_NOTIFICATION_EVENT_AI_TEAM_TICKET_SUBMITTED, "ai_team_person", ["reviewer@example.com"]),
        ):
            with self.subTest(event=event):
                payload = services.build_support_notification_webhook_payload(event, ticket)
                self.assertEqual(payload["recipientType"], recipient_type)
                self.assertEqual(payload["recipients"], recipients)
                self.assertEqual(payload["ticket"]["id"], "KBC-000024")

    def test_multipart_retry_preserves_evidence_and_ticket_delivery_key(self):
        payload = {
            "event": services.SUPPORT_NOTIFICATION_EVENT_AI_TEAM_TICKET_SUBMITTED,
            "ticket": {"id": "KBC-000024"},
            "recipientType": "ai_team_person",
        }
        attachment = {"name": "evidence.txt", "mimeType": "text/plain", "dataUrl": "data:text/plain;base64,aGVsbG8="}
        with (
            patch.object(services, "get_support_notification_webhook_url", return_value="https://example.test/webhook"),
            patch.object(services, "execute_http_request", side_effect=[
                (True, False, 503, {}), (True, True, 200, {}),
            ]) as send,
            patch.object(services.time, "sleep"),
        ):
            result = services.send_support_notification_webhook(payload, attachments=[attachment])

        self.assertTrue(result["delivered"])
        self.assertEqual(result["attempts"], 2)
        expected_key = "ai_team_ticket_submitted:KBC-000024:ai_team_person"
        self.assertEqual(result["deliveryKey"], expected_key)
        for call in send.call_args_list:
            request = call.args[0]
            self.assertEqual(request.get_header("X-support-delivery-key"), expected_key)
            self.assertIn(b'filename="evidence.txt"', request.data)
            self.assertIn(b"hello", request.data)

    def test_multipart_timeout_is_not_retried(self):
        with (
            patch.object(services, "get_support_notification_webhook_url", return_value="https://example.test/webhook"),
            patch.object(services, "post_multipart_webhook", return_value=(True, False, None, {"message": "Request timed out."})) as send,
            patch.object(services.time, "sleep") as sleep,
        ):
            result = services.send_support_notification_webhook(
                {"event": "ai_team_ticket_submitted", "ticket": {"id": "KBC-000024"}},
                attachments=[{"name": "evidence.txt", "dataUrl": "data:text/plain;base64,aGVsbG8="}],
            )
        self.assertFalse(result["delivered"])
        self.assertEqual(result["attempts"], 1)
        send.assert_called_once()
        sleep.assert_not_called()


class LmsRequesterWorkflowTests(SimpleTestCase):
    def test_lms_learner_has_the_same_submission_limits_as_a_legacy_learner(self):
        for source in (services.KBC_USERS_DATA_REQUESTER_SOURCE, services.LMS_LEARNERS_REQUESTER_SOURCE):
            with self.subTest(source=source):
                self.assertFalse(services.can_requester_submit_coverage_ticket(source))
                self.assertFalse(services.can_requester_submit_ai_team_ticket(source))
                self.assertFalse(services.can_requester_submit_for_learner("user", source))
                self.assertTrue(services.can_requester_submit_for_learner("tutor", source))

    def test_lms_learner_is_a_valid_on_behalf_ticket_target(self):
        learner = {"id": 9, "source": "lms_learners", "email": "learner@example.com"}
        with patch.object(services, "fetch_local_learner_by_id", return_value=learner):
            self.assertEqual(services.resolve_submitted_for_learner(
                9, requester_role="tutor", requester_source="lms_learners",
            ), learner)

    def test_ticket_source_keeps_lms_identity_after_account_sync(self):
        self.assertEqual(services.get_ticket_requester_source(
            {"requester_role": "user", "requester_source": "support_portal_requester"},
            learner_source="lms_learners",
        ), "lms_learners")
