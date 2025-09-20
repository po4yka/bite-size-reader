import json
import os
import tempfile
import unittest

from app.db.database import Database


class TestDatabaseHelpers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "app.db")
        self.db = Database(self.db_path)
        self.db.migrate()

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_request_and_fetch_by_hash(self):
        rid = self.db.create_request(
            type_="url",
            status="pending",
            correlation_id="abc123",
            chat_id=100,
            user_id=200,
            input_url="https://example.com",
            normalized_url="https://example.com",
            dedupe_hash="abc",
            route_version=1,
        )
        self.assertIsInstance(rid, int)
        row = self.db.get_request_by_dedupe_hash("abc")
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], rid)
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["correlation_id"], "abc123")

        # Update status and lang
        self.db.update_request_status(rid, "ok")
        self.db.update_request_lang_detected(rid, "en")
        self.db.update_request_correlation_id(rid, "zzz999")
        row2 = self.db.get_request_by_dedupe_hash("abc")
        self.assertEqual(row2["status"], "ok")
        self.assertEqual(row2["lang_detected"], "en")
        self.assertEqual(row2["correlation_id"], "zzz999")

    def test_crawl_result_helpers(self):
        rid = self.db.create_request(
            type_="url",
            status="pending",
            correlation_id=None,
            chat_id=None,
            user_id=None,
            route_version=1,
        )
        cid = self.db.insert_crawl_result(
            request_id=rid,
            source_url="https://example.com",
            endpoint="/v1/scrape",
            http_status=200,
            status="ok",
            options_json=json.dumps({}),
            correlation_id="fc-123",
            content_markdown="# md",
            content_html=None,
            structured_json=json.dumps({}),
            metadata_json=json.dumps({}),
            links_json=json.dumps({}),
            screenshots_paths_json=None,
            raw_response_json=json.dumps({}),
            latency_ms=123,
            error_text=None,
        )
        self.assertIsInstance(cid, int)
        row = self.db.get_crawl_result_by_request(rid)
        self.assertIsNotNone(row)
        self.assertEqual(row["http_status"], 200)
        self.assertEqual(row["content_markdown"], "# md")
        self.assertEqual(row["correlation_id"], "fc-123")

    def test_summary_upsert(self):
        rid = self.db.create_request(
            type_="url",
            status="pending",
            correlation_id=None,
            chat_id=None,
            user_id=None,
            route_version=1,
        )
        v1 = self.db.upsert_summary(request_id=rid, lang="en", json_payload=json.dumps({"a": 1}))
        self.assertEqual(v1, 1)
        row = self.db.get_summary_by_request(rid)
        self.assertIsNotNone(row)
        self.assertEqual(row["version"], 1)
        self.assertEqual(row["lang"], "en")
        self.assertIsNone(row["insights_json"])

        v2 = self.db.upsert_summary(request_id=rid, lang="en", json_payload=json.dumps({"a": 2}))
        self.assertEqual(v2, 2)
        row2 = self.db.get_summary_by_request(rid)
        self.assertEqual(row2["version"], 2)

        insights_payload = json.dumps({"topic_overview": "Context", "new_facts": []})
        self.db.update_summary_insights(rid, insights_payload)
        row3 = self.db.get_summary_by_request(rid)
        self.assertEqual(row3["insights_json"], insights_payload)

    def test_insert_llm_and_telegram_and_audit(self):
        rid = self.db.create_request(
            type_="forward",
            status="pending",
            correlation_id=None,
            chat_id=1,
            user_id=2,
            route_version=1,
        )
        # Telegram message
        mid = self.db.insert_telegram_message(
            request_id=rid,
            message_id=10,
            chat_id=1,
            date_ts=1700000000,
            text_full="hello",
            entities_json=json.dumps([{"type": "bold"}]),
            media_type="photo",
            media_file_ids_json=json.dumps(["file_1"]),
            forward_from_chat_id=7,
            forward_from_chat_type="channel",
            forward_from_chat_title="Title",
            forward_from_message_id=5,
            forward_date_ts=1700000001,
            telegram_raw_json=json.dumps({"k": "v"}),
        )
        self.assertIsInstance(mid, int)
        row = self.db.fetchone("SELECT * FROM telegram_messages WHERE request_id = ?", (rid,))
        self.assertIsNotNone(row)
        self.assertEqual(row["media_type"], "photo")

        # LLM call
        lid = self.db.insert_llm_call(
            request_id=rid,
            provider="openrouter",
            model="m",
            endpoint="/api/v1/chat/completions",
            request_headers_json=json.dumps({"Authorization": "REDACTED"}),
            request_messages_json=json.dumps([{"role": "user", "content": "hi"}]),
            response_text="{}",
            response_json=json.dumps({"choices": []}),
            tokens_prompt=1,
            tokens_completion=2,
            cost_usd=0.001,
            latency_ms=50,
            status="ok",
            error_text=None,
            structured_output_used=True,
            structured_output_mode="json_schema",
            error_context_json=json.dumps({"status_code": 200}),
        )
        self.assertIsInstance(lid, int)
        lrow = self.db.fetchone("SELECT * FROM llm_calls WHERE id = ?", (lid,))
        self.assertIsNotNone(lrow)
        self.assertEqual(lrow["status"], "ok")
        self.assertEqual(lrow["tokens_completion"], 2)
        self.assertEqual(lrow["structured_output_used"], 1)
        self.assertEqual(lrow["structured_output_mode"], "json_schema")
        self.assertEqual(json.loads(lrow["error_context_json"]), {"status_code": 200})

        # Audit
        aid = self.db.insert_audit_log(
            level="INFO", event="test", details_json=json.dumps({"x": 1})
        )
        self.assertIsInstance(aid, int)
        arow = self.db.fetchone("SELECT * FROM audit_logs WHERE id = ?", (aid,))
        self.assertIsNotNone(arow)
        self.assertEqual(arow["level"], "INFO")


if __name__ == "__main__":
    unittest.main()
