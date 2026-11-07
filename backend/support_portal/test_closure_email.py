from unittest.mock import patch

from django.test import SimpleTestCase

from . import graph_mail, services


class ClosureEmailRenderingTests(SimpleTestCase):
    def test_custom_subject_and_message_are_rendered_safely(self):
        subject, html = graph_mail.render_notification_email({
            "event": services.SUPPORT_NOTIFICATION_EVENT_QUICK_TICKET_CLOSED,
            "requester": {"name": "Ayman"},
            "ticket": {"id": "KBC-000123", "status": "Closed"},
            "closureEmail": {
                "subject": "Resolved: KBC-000123",
                "message": "First line\n<script>alert('x')</script>",
            },
        })

        self.assertEqual(subject, "Resolved: KBC-000123")
        self.assertIn("First line<br>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>alert", html)

    @patch.object(services, "get_admin_ticket_detail_response")
    def test_draft_lists_server_resolved_recipients_and_defaults_to_editable_message(self, detail_response):
        detail_response.return_value = {
            "ticket": {
                "id": "KBC-000123",
                "requesterName": "Requester",
                "learnerName": "Requester",
                "email": "requester@example.com",
                "subject": "Portal help",
                "category": "Technical",
                "technicalSubcategory": "LMS",
                "submittedForLearner": {
                    "fullName": "Learner",
                    "email": "learner@example.com",
                    "notifyByEmail": True,
                },
            }
        }

        draft = services.get_admin_ticket_closure_email_draft("KBC-000123", {"id": 7})

        self.assertTrue(draft["available"])
        self.assertEqual(
            [recipient["email"] for recipient in draft["recipients"]],
            ["requester@example.com", "learner@example.com"],
        )
        self.assertEqual(draft["message"], graph_mail.default_closure_message())
        self.assertIn("KBC-000123", draft["subject"])
        self.assertIn("Ticket closed", draft["previewHtml"])
