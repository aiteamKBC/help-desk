from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, override_settings


class KnowledgeBaseApiTests(SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.temp_dir = TemporaryDirectory()
        self.kb_root = Path(self.temp_dir.name)
        (self.kb_root / "Articles").mkdir(parents=True, exist_ok=True)
        (self.kb_root / "Evidence").mkdir(parents=True, exist_ok=True)
        self.override = override_settings(KNOWLEDGE_BASE_ROOT=self.kb_root)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_list_articles_reads_embedded_article_json(self):
        (self.kb_root / "Articles" / "reset-password.html").write_text(
            (
                "<!doctype html><html><head><title>Reset Password</title></head><body>"
                '<template id="kb-article-json">'
                "{&quot;title&quot;:&quot;Reset Password&quot;,&quot;keywords&quot;:&quot;lms, password&quot;,"
                "&quot;sections&quot;:{&quot;inquiry&quot;:&quot;Help&quot;,&quot;summary&quot;:&quot;Do this&quot;,"
                "&quot;steps&quot;:&quot;1. Reset&quot;,&quot;resources&quot;:&quot;Portal&quot;},"
                "&quot;attachments&quot;:{&quot;inquiry&quot;:[],&quot;summary&quot;:[],&quot;steps&quot;:[],&quot;resources&quot;:[]}}"
                "</template></body></html>"
            ),
            encoding="utf-8",
        )

        response = self.client.get("/api/knowledge-base/articles")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["articles"]), 1)
        self.assertEqual(payload["articles"][0]["title"], "Reset Password")
        self.assertEqual(payload["articles"][0]["fileName"], "reset-password.html")
        self.assertEqual(payload["articles"][0]["sections"]["steps"], "1. Reset")

    def test_post_article_saves_html_and_evidence(self):
        html = (
            "<!doctype html><html><body><template id=\"kb-article-json\">"
            "{&quot;title&quot;:&quot;New Article&quot;,&quot;sections&quot;:{},&quot;attachments&quot;:{}}"
            "</template></body></html>"
        )
        response = self.client.post(
            "/api/knowledge-base/articles",
            data=json.dumps(
                {
                    "filename": "new-article.html",
                    "html": html,
                    "evidence": [
                        {
                            "name": "proof.txt",
                            "dataUrl": "data:text/plain;base64,SGVsbG8gS0I=",
                        }
                    ],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue((self.kb_root / "Articles" / "new-article.html").exists())
        self.assertEqual((self.kb_root / "Evidence" / "proof.txt").read_text(encoding="utf-8"), "Hello KB")

    def test_delete_article_moves_file_to_archive_bin(self):
        article_path = self.kb_root / "Articles" / "archive-me.html"
        article_path.write_text("<!doctype html><html><head><title>Archive me</title></head></html>", encoding="utf-8")

        response = self.client.delete(
            "/api/knowledge-base/articles",
            data=json.dumps({"filename": "archive-me.html"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(article_path.exists())
        self.assertTrue((self.kb_root / "Articles" / "Bin" / "archive-me.html").exists())

    def test_asset_endpoint_blocks_bin_access(self):
        archived_file = self.kb_root / "Articles" / "Bin"
        archived_file.mkdir(parents=True, exist_ok=True)
        (archived_file / "hidden.html").write_text("secret", encoding="utf-8")

        response = self.client.get("/api/knowledge-base/assets/Articles/Bin/hidden.html")

        self.assertEqual(response.status_code, 404)
