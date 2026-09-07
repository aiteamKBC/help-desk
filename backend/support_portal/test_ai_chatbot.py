from django.test import SimpleTestCase
from unittest.mock import patch

from support_portal.ai.chatbot import build_retrieval_query, handle_chat
from support_portal.ai.classifier import classify
from support_portal.ai.session import get_session_key


class CharlyClassifierTests(SimpleTestCase):
    def test_greeting_direct_response(self):
        result = classify({"message": "hello", "learner": {"fullName": "Ayman Badewi"}, "messages": [{"sender": "user", "text": "hello"}]})
        self.assertEqual(result.route, "greeting")
        self.assertEqual(result.direct_reply, "Hi Ayman, Charly here. What can I help you with?")

    def test_closing_direct_response(self):
        result = classify({"message": "thanks"})
        self.assertEqual(result.route, "closing")
        self.assertEqual(
            result.direct_reply,
            "Thank you for contacting Kent Help Desk. Get in touch again whenever you need support.",
        )

    def test_human_request_direct_response(self):
        result = classify({"message": "I want to speak to a human"})
        self.assertEqual(result.route, "human")
        self.assertIn("Live Agent button", result.direct_reply)

    def test_booking_direct_response(self):
        result = classify({"message": "I want to book a session"})
        self.assertEqual(result.route, "booking")
        self.assertIn("Book Session button", result.direct_reply)

    def test_teams_explicit_platform(self):
        self.assertEqual(classify({"message": "how to open camere in teams"}).route, "teams")

    def test_ticket_subcategory_teams(self):
        self.assertEqual(classify({"message": "my camera does not work", "ticket": {"technicalSubcategory": "Teams"}}).route, "teams")

    def test_top_level_technical_subcategory_teams(self):
        self.assertEqual(classify({"message": "my camera does not work", "technicalSubcategory": "Teams"}).route, "teams")

    def test_aptem_route(self):
        self.assertEqual(classify({"message": "I cannot upload evidence in Aptem"}).route, "aptem")

    def test_moodle_route(self):
        self.assertEqual(classify({"message": "I cannot see my assignment on Moodle"}).route, "moodle")

    def test_sticky_follow_up(self):
        self.assertEqual(classify({"message": "still not working"}, previous_route="teams").route, "teams")

    def test_explicit_override(self):
        self.assertEqual(classify({"message": "actually my Aptem isn't working"}, previous_route="teams").route, "aptem")

    def test_session_key_ticket_id_priority(self):
        self.assertEqual(
            get_session_key({"ticketId": "fallback", "sessionId": "session", "learner": {"email": "a@example.com"}, "ticket": {"id": "KBC-1"}}),
            "KBC-1",
        )

    def test_missing_ticket_and_learner_do_not_crash(self):
        self.assertEqual(classify({"message": "my issue continues"}).route, "general")
        self.assertEqual(get_session_key({}), "guest:web")

    def test_retrieval_query_keeps_inquiry_and_main_page_ui_hints(self):
        query = build_retrieval_query(
            {
                "message": "I am on the main page",
                "ticket": {
                    "category": "Technical",
                    "technicalSubcategory": "LMS",
                    "inquiry": "How do I submit Assignment 7?",
                },
                "messages": [
                    {"sender": "user", "text": "I need to upload an assignment"},
                    {"sender": "bot", "text": "Which LMS page are you on right now?"},
                ],
            }
        )

        self.assertIn("How do I submit Assignment 7?", query)
        self.assertIn("I am on the main page", query)
        self.assertIn("Learner Workspace Overview Continue Learning", query)


class CharlyDirectPathTests(SimpleTestCase):
    @patch("support_portal.ai.chatbot.save_last_route")
    @patch("support_portal.ai.chatbot.generate_reply")
    @patch("support_portal.ai.chatbot.search_knowledge_base")
    @patch("support_portal.ai.chatbot.get_last_route", return_value="teams")
    def test_direct_closing_does_not_call_rag_or_openai_or_overwrite_route(
        self,
        _get_last_route,
        search_knowledge_base,
        generate_reply,
        save_last_route,
    ):
        response = handle_chat({"message": "thanks", "ticket": {"id": "KBC-1"}})

        self.assertTrue(response["success"])
        self.assertEqual(response["route"], "closing")
        self.assertEqual(
            response["reply"],
            "Thank you for contacting Kent Help Desk. Get in touch again whenever you need support.",
        )
        search_knowledge_base.assert_not_called()
        generate_reply.assert_not_called()
        save_last_route.assert_not_called()

    @patch("support_portal.ai.chatbot.save_last_route")
    @patch("support_portal.ai.chatbot.generate_reply", return_value="Open Teams settings and check the camera permission.")
    @patch("support_portal.ai.chatbot.search_knowledge_base", return_value=[{"text": "Teams camera help", "metadata": {}}])
    @patch("support_portal.ai.chatbot.get_last_route", return_value="")
    def test_teams_route_uses_single_generation(
        self,
        _get_last_route,
        _search_knowledge_base,
        generate_reply,
        save_last_route,
    ):
        response = handle_chat({"message": "how to open camere in teams", "ticket": {"id": "KBC-2"}})

        self.assertTrue(response["success"])
        self.assertEqual(response["route"], "teams")
        self.assertIn("Open Teams settings", response["reply"])
        self.assertEqual(generate_reply.call_count, 1)
        save_last_route.assert_called_once_with("KBC-2", "teams")
