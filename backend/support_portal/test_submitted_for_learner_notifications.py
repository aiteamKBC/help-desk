from unittest.mock import patch

from django.test import SimpleTestCase

from support_portal import graph_mail, services


class SubmittedForLearnerNotificationTests(SimpleTestCase):
    def setUp(self):
        self.ticket = {
            "id": 12,
            "public_id": "KBC-000012",
            "email": "submitter@example.com",
            "learner_name": "Coach",
            "subject": "Help",
            "metadata": {
                "submitted_for_learner": {
                    "id": 42, "fullName": "Learner", "email": "stale@example.com",
                    "notificationEmail": "attacker@example.com", "notifyByEmail": True,
                },
            },
        }

    def test_creation_and_closure_use_current_learner_table_email(self):
        with (
            patch.object(services, "fetch_local_learner_by_id", return_value={"id": 42, "email": "official@example.com"}) as lookup,
            patch.object(services, "queue_support_notification_delivery") as queue,
        ):
            services.queue_submitted_for_learner_notification(self.ticket)
            services.queue_submitted_for_learner_notification(self.ticket, closed=True, status="Closed")
        self.assertEqual(lookup.call_count, 2)
        self.assertEqual(queue.call_count, 2)
        for call in queue.call_args_list:
            self.assertEqual(call.kwargs["payload"]["recipients"], ["official@example.com"])
            self.assertEqual(call.kwargs["payload"]["recipientType"], "submitted_for_learner")
        self.assertEqual(queue.call_args_list[0].kwargs["event"], "submitted_for_learner_created")
        self.assertEqual(queue.call_args_list[1].kwargs["event"], "submitted_for_learner_closed")

    def test_opt_out_does_not_queue_creation_or_closure_email(self):
        self.ticket["metadata"]["submitted_for_learner"]["notifyByEmail"] = False

        with (
            patch.object(services, "fetch_local_learner_by_id", return_value={"id": 42, "email": "official@example.com"}) as lookup,
            patch.object(services, "queue_support_notification_delivery") as queue,
        ):
            services.queue_submitted_for_learner_notification(self.ticket)
            services.queue_submitted_for_learner_notification(self.ticket, closed=True)

        lookup.assert_not_called()
        queue.assert_not_called()

    def test_requester_email_is_not_duplicated_to_the_same_address(self):
        with (
            patch.object(services, "fetch_local_learner_by_id", return_value={"id": 42, "email": "submitter@example.com"}),
            patch.object(services, "queue_support_notification_delivery") as queue,
        ):
            services.queue_submitted_for_learner_notification(self.ticket)

        queue.assert_not_called()

    def test_rendered_mail_has_no_admin_ticket_link(self):
        payload = services.build_support_notification_webhook_payload("submitted_for_learner_closed", self.ticket, status="Closed")
        payload["recipientType"] = "submitted_for_learner"
        subject, html = graph_mail.render_notification_email(payload)
        self.assertIn("KBC-000012", subject)
        self.assertIn("resolved and closed", html)
        self.assertNotIn("/admin", html)
