"""Offline regression tests: no production database or model calls."""
from contextlib import nullcontext
from copy import deepcopy
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from support_portal import chatbot
from support_portal.lms_knowledge import (
    SOURCE_KEY, build_chunks, digest, validate_embeddings,
)
from support_portal.management.commands.import_lms_knowledge import matches_version


GUIDE = """# LearningOS
## How to use this document (instructions for the assistant)
Only describe documented features.
## 3. Learners
### 3.1 Onboarding
Complete the learner checklist.
## 5. Coaches
### Attendance
Mark your caseload attendance.
## 6. Other staff roles
### Tutor
Open My Teaching.
## Not live yet
Messages is disabled. Demo workspaces are not live.
"""


class LmsChunkTests(SimpleTestCase):
    def test_sections_keep_role_ancestry_and_guardrails(self):
        chunks = build_chunks(GUIDE, "guide.md")
        self.assertEqual(len(chunks), 5)
        self.assertEqual([c["metadata"]["audiences"] for c in chunks],
                         [["all"], ["learner"], ["coach"], ["tutor"], ["all"]])
        self.assertEqual(sum(c["metadata"]["guardrail"] for c in chunks), 2)
        for i, chunk in enumerate(chunks):
            self.assertEqual(chunk["metadata"]["source_key"], SOURCE_KEY)
            self.assertEqual(chunk["metadata"]["source_hash"], digest(GUIDE))
            self.assertEqual(chunk["metadata"]["chunk_index"], i)
            self.assertEqual(chunk["metadata"]["chunk_hash"], digest(chunk["text"]))

    def test_long_lines_are_not_truncated(self):
        body = "x" * 6500
        chunks = build_chunks("# Title\n" + body, "guide.md")
        self.assertEqual("".join(c["text"].split("\n\n", 1)[1] for c in chunks), body)
        self.assertEqual(len(chunks), 3)

    def test_code_fence_heading_is_not_a_section(self):
        chunks = build_chunks("# Title\n```text\n## not a heading\n```\nEnd.", "guide.md")
        self.assertEqual(len(chunks), 1)
        self.assertIn("## not a heading", chunks[0]["text"])

    def test_empty_or_heading_only_input_rejected(self):
        for text in ("", "# Empty\n---"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                build_chunks(text, "guide.md")

    def test_embeddings_require_finite_nonzero_1536_dimensions(self):
        validate_embeddings([[1.0] * 1536], 1)
        for vectors in ([], [[1.0]], [[0.0] * 1536], [[float("nan")] * 1536], [[float("inf")] * 1536]):
            with self.subTest(length=len(vectors)), self.assertRaises(ValueError):
                validate_embeddings(vectors, 1)

    def test_import_matching_checks_full_source_chunks_model_and_dimensions(self):
        chunks = build_chunks(GUIDE, "guide.md")
        rows = [(1, GUIDE, {"record_type": "document", "status": "active"}, None)] + [
            (i + 2, c["text"], {**c["metadata"], "embedding_model": "test"}, 1536)
            for i, c in enumerate(chunks)
        ]
        self.assertTrue(matches_version(rows, GUIDE, chunks, "test"))
        self.assertFalse(matches_version(rows[:-1], GUIDE, chunks, "test"))
        self.assertFalse(matches_version(rows, GUIDE + "changed", chunks, "test"))
        self.assertFalse(matches_version(rows, GUIDE, chunks, "different-model"))
        wrong = deepcopy(rows)
        wrong[-1][2]["status"] = "archived"
        self.assertFalse(matches_version(wrong, GUIDE, chunks, "test"))
        wrong = rows[:-1] + [(*rows[-1][:3], None)]
        self.assertFalse(matches_version(wrong, GUIDE, chunks, "test"))


class LmsRetrievalTests(SimpleTestCase):
    def test_learning_questions_use_new_lms_and_explicit_other_products_still_work(self):
        cases = {
            "How do I upload evidence?": "lms",
            "How do I log OTJ hours?": "lms",
            "How do I mark attendance?": "lms",
            "Where is my calendar?": "lms",
            "I am a tutor, where is My Teaching?": "lms",
            "How do I use Moodle?": "lms",
            "انا كوتش اسجل الحضور ازاي؟": "lms",
            "Aptem dashboard help": "aptem",
            "My Teams microphone is not working": "teams",
            "How do I log in to the support portal?": "support",
            "What is my support ticket status?": "support",
            "Something unknown": "general",
        }
        for question, route in cases.items():
            with self.subTest(question=question):
                self.assertEqual(chatbot.classify_route(question), route)
        self.assertNotIn("moodle_knowledge_base", chatbot.ALLOWED_KB_TABLES)

    def run_search(self, route):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.side_effect = [
            [("Current help", .2, {"source_key": SOURCE_KEY})],
            [("Messages is disabled", {"guardrail": True})],
        ]
        with patch.object(chatbot, "connection", conn), patch.object(
            chatbot.transaction, "atomic", return_value=nullcontext()
        ), patch.object(chatbot, "embed_query", return_value=[1.0] * 1536):
            results = chatbot.search_knowledge_base(route, "How do I start?", top_k=1)
        return results, cursor.execute.call_args_list

    def test_moodle_legacy_route_never_queries_archived_table(self):
        results, calls = self.run_search("moodle")
        sql = "\n".join(c.args[0] for c in calls)
        self.assertNotIn("moodle_knowledge_base", sql)
        self.assertIn("metadata->>'source_key'=%s", sql)
        self.assertIn("metadata->>'archived'", sql)
        self.assertIn("metadata->>'status'", sql)
        self.assertEqual(len(results), 2)  # guardrails survive top_k
        self.assertTrue(results[-1]["guardrail"])
        self.assertIsNone(results[-1]["distance"])

    def test_support_search_does_not_use_lms_document(self):
        results, calls = self.run_search("support")
        self.assertEqual(len(results), 1)
        self.assertIn("IS DISTINCT FROM %s", "\n".join(c.args[0] for c in calls))

    def test_coach_and_tutor_get_direct_role_help(self):
        for role in ("coach", "tutor"):
            with self.subTest(role=role), patch.object(chatbot, "search_knowledge_base", return_value=[
                {"text": "Role guidance", "distance": .2},
                {"text": "Messages is disabled", "distance": None, "guardrail": True},
            ]) as search, patch.object(chatbot, "_chat_completion", return_value="Open your workspace.") as completion:
                response = chatbot.generate_assistant_reply(f"I am a {role}. Where do I start?")
                self.assertFalse(response["escalate"])
                self.assertIn(role + " workspace:", search.call_args.args[1])
                messages = completion.call_args.args[0]
                self.assertIn("helping a " + role, messages[0]["content"])
                self.assertIn("Messages is disabled", messages[-1]["content"])

    def test_guardrails_alone_do_not_claim_a_matching_answer(self):
        # Past the opening turns, so the escalation gate is not what is under test.
        history = [
            {"sender": "user", "text": "The portal is misbehaving"},
            {"sender": "bot", "text": "Which page are you on?"},
            {"sender": "user", "text": "My Learning"},
        ]
        with patch.object(chatbot, "search_knowledge_base", return_value=[
            {"text": "Not live yet", "distance": None, "guardrail": True},
        ]), patch.object(chatbot, "_chat_completion", return_value="Please contact your programme team."):
            response = chatbot.generate_assistant_reply("An undocumented LMS problem", history=history)
        self.assertTrue(response["escalate"])
        self.assertIsNone(response["kbDistance"])

    def test_opening_turns_try_before_offering_escalation(self):
        """An unmatched first message means scope it, not hand it to a human."""
        with patch.object(chatbot, "search_knowledge_base", return_value=[
            {"text": "Not live yet", "distance": None, "guardrail": True},
        ]), patch.object(chatbot, "_chat_completion", return_value="Please contact your programme team."):
            response = chatbot.generate_assistant_reply("An undocumented LMS problem")
        self.assertFalse(response["escalate"])

    def test_asking_for_a_human_escalates_on_the_first_message(self):
        """The gate holds back guesswork, never a learner who asked outright."""
        with patch.object(chatbot, "search_knowledge_base", return_value=[
            {"text": "Not live yet", "distance": None, "guardrail": True},
        ]), patch.object(chatbot, "_chat_completion", return_value="I'll get someone to help."):
            response = chatbot.generate_assistant_reply("I want to speak to a human")
        self.assertTrue(response["escalate"])

    def test_follow_up_keeps_self_described_role_and_allows_switch(self):
        with patch.object(chatbot, "search_knowledge_base", return_value=[
            {"text": "Role guidance", "distance": .2},
        ]), patch.object(chatbot, "_chat_completion", return_value="Documented steps.") as completion:
            history = [{"sender": "user", "text": "I am a tutor."}]
            chatbot.generate_assistant_reply("Where do I see my next session?", history=history)
            self.assertIn("helping a tutor", completion.call_args.args[0][0]["content"])
            chatbot.generate_assistant_reply("I am a coach now. Where is attendance?", history=history)
            self.assertIn("helping a coach", completion.call_args.args[0][0]["content"])
