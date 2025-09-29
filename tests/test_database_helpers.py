import copy
import json
import os
import sqlite3
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

    def test_create_backup_copy_writes_snapshot(self):
        backup_dir = os.path.join(self.tmp.name, "backups")
        backup_path = os.path.join(backup_dir, "snapshot.db")

        created = self.db.create_backup_copy(backup_path)

        self.assertTrue(os.path.exists(created))
        with sqlite3.connect(created) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='requests'"
            ).fetchone()
            self.assertIsNotNone(row)

    def test_create_backup_copy_rejects_memory_db(self):
        mem_db = Database(":memory:")
        mem_db.migrate()

        with self.assertRaises(ValueError):
            mem_db.create_backup_copy(os.path.join(self.tmp.name, "memory.db"))

    def test_create_backup_copy_requires_source_file(self):
        db = Database(os.path.join(self.tmp.name, "missing.db"))

        with self.assertRaises(FileNotFoundError):
            db.create_backup_copy(os.path.join(self.tmp.name, "missing-backup.db"))

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

    def test_create_request_handles_duplicate_hash_race(self):
        first_id = self.db.create_request(
            type_="url",
            status="pending",
            correlation_id="cid-1",
            chat_id=1,
            user_id=1,
            input_url="https://example.com/path",
            normalized_url="https://example.com/path",
            dedupe_hash="shared-hash",
            route_version=1,
        )

        second_id = self.db.create_request(
            type_="url",
            status="pending",
            correlation_id="cid-2",
            chat_id=1,
            user_id=1,
            input_url="https://example.com/path",
            normalized_url="https://example.com/path",
            dedupe_hash="shared-hash",
            route_version=1,
        )

        self.assertEqual(first_id, second_id)

        row = self.db.get_request_by_dedupe_hash("shared-hash")
        self.assertEqual(row["id"], first_id)
        # Latest correlation id should be persisted
        self.assertEqual(row["correlation_id"], "cid-2")

        # Only one record should exist
        count = self.db.fetchone(
            "SELECT COUNT(*) AS c FROM requests WHERE dedupe_hash = ?", ("shared-hash",)
        )
        self.assertEqual(count["c"], 1)

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
            options_json={},
            correlation_id="fc-123",
            content_markdown="# md",
            content_html=None,
            structured_json={},
            metadata_json={},
            links_json={},
            screenshots_paths_json=None,
            firecrawl_success=True,
            firecrawl_error_code=None,
            firecrawl_error_message=None,
            firecrawl_details_json=None,
            raw_response_json=None,
            latency_ms=123,
            error_text=None,
        )
        self.assertIsInstance(cid, int)
        row = self.db.get_crawl_result_by_request(rid)
        self.assertIsNotNone(row)
        self.assertEqual(row["http_status"], 200)
        self.assertEqual(row["content_markdown"], "# md")
        self.assertEqual(row["correlation_id"], "fc-123")
        self.assertTrue(row["firecrawl_success"])
        self.assertIsNone(row["raw_response_json"])

    def test_summary_upsert(self):
        rid = self.db.create_request(
            type_="url",
            status="pending",
            correlation_id=None,
            chat_id=None,
            user_id=None,
            route_version=1,
        )
        v1 = self.db.upsert_summary(request_id=rid, lang="en", json_payload={"a": 1})
        self.assertEqual(v1, 1)
        row = self.db.get_summary_by_request(rid)
        self.assertIsNotNone(row)
        self.assertEqual(row["version"], 1)
        self.assertEqual(row["lang"], "en")
        self.assertIsNone(row["insights_json"])

        v2 = self.db.upsert_summary(request_id=rid, lang="en", json_payload={"a": 2})
        self.assertEqual(v2, 2)
        row2 = self.db.get_summary_by_request(rid)
        self.assertEqual(row2["version"], 2)

        insights_payload = {"topic_overview": "Context", "new_facts": []}
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
            entities_json=[{"type": "bold"}],
            media_type="photo",
            media_file_ids_json=["file_1"],
            forward_from_chat_id=7,
            forward_from_chat_type="channel",
            forward_from_chat_title="Title",
            forward_from_message_id=5,
            forward_date_ts=1700000001,
            telegram_raw_json={"k": "v"},
        )
        self.assertIsInstance(mid, int)
        row = self.db.fetchone("SELECT * FROM telegram_messages WHERE request_id = ?", (rid,))
        self.assertIsNotNone(row)
        self.assertEqual(row["media_type"], "photo")
        self.assertEqual(row["chat_id"], 1)

        # LLM call
        lid = self.db.insert_llm_call(
            request_id=rid,
            provider="openrouter",
            model="m",
            endpoint="/api/v1/chat/completions",
            request_headers_json={"Authorization": "REDACTED"},
            request_messages_json=[{"role": "user", "content": "hi"}],
            response_text="{}",
            response_json={"choices": []},
            tokens_prompt=1,
            tokens_completion=2,
            cost_usd=0.001,
            latency_ms=50,
            status="ok",
            error_text=None,
            structured_output_used=True,
            structured_output_mode="json_schema",
            error_context_json={"status_code": 200},
        )
        self.assertIsInstance(lid, int)
        lrow = self.db.fetchone("SELECT * FROM llm_calls WHERE id = ?", (lid,))
        self.assertIsNotNone(lrow)
        self.assertEqual(lrow["status"], "ok")
        self.assertEqual(lrow["tokens_completion"], 2)
        self.assertEqual(lrow["structured_output_used"], 1)
        self.assertEqual(lrow["structured_output_mode"], "json_schema")
        self.assertEqual(json.loads(lrow["error_context_json"]), {"status_code": 200})
        self.assertIsNone(lrow["response_text"])
        self.assertIsNone(lrow["response_json"])
        self.assertEqual(lrow["openrouter_response_text"], "{}")
        self.assertEqual(
            json.loads(lrow["openrouter_response_json"] or "{}"),
            {"choices": []},
        )

        # Audit
        aid = self.db.insert_audit_log(level="INFO", event="test", details_json={"x": 1})
        self.assertIsInstance(aid, int)
        arow = self.db.fetchone("SELECT * FROM audit_logs WHERE id = ?", (aid,))
        self.assertIsNotNone(arow)
        self.assertEqual(arow["level"], "INFO")

    def test_verify_processing_integrity(self):
        base_summary = {
            "summary_250": "Short summary.",
            "summary_1000": "Medium summary providing additional detail.",
            "tldr": "Longer summary text.",
            "key_ideas": ["Idea"],
            "topic_tags": ["#tag"],
            "entities": {
                "people": [],
                "organizations": [],
                "locations": [],
            },
            "estimated_reading_time_min": 5,
            "key_stats": [],
            "answered_questions": [],
            "readability": {"method": "FK", "score": 50.0, "level": "Standard"},
            "seo_keywords": [],
            "metadata": {
                "title": "Title",
                "canonical_url": "https://example.com/article",
                "domain": "example.com",
                "author": "Author",
                "published_at": "2024-01-01",
                "last_updated": "2024-01-01",
            },
            "extractive_quotes": [],
            "highlights": [],
            "questions_answered": [],
            "categories": [],
            "topic_taxonomy": [],
            "hallucination_risk": "low",
            "confidence": 1.0,
            "forwarded_post_extras": None,
            "key_points_to_remember": [],
        }

        rid_good = self.db.create_request(
            type_="url",
            status="ok",
            correlation_id="good",
            chat_id=1,
            user_id=1,
            input_url="https://example.com/good",
            normalized_url="https://example.com/good",
            route_version=1,
        )
        self.db.insert_summary(
            request_id=rid_good,
            lang="en",
            json_payload=base_summary,
        )
        self.db.insert_crawl_result(
            request_id=rid_good,
            source_url="https://example.com/good",
            endpoint="/v1/scrape",
            http_status=200,
            status="ok",
            options_json={},
            correlation_id="fc-good",
            content_markdown="# md",
            content_html=None,
            structured_json={},
            metadata_json={},
            links_json=["https://example.com/other"],
            screenshots_paths_json=None,
            firecrawl_success=True,
            firecrawl_error_code=None,
            firecrawl_error_message=None,
            firecrawl_details_json=None,
            raw_response_json=None,
            latency_ms=100,
            error_text=None,
        )

        bad_summary = copy.deepcopy(base_summary)
        bad_summary.pop("summary_1000", None)
        bad_summary.pop("tldr", None)
        bad_summary["summary_250"] = ""
        bad_summary.pop("metadata", None)

        rid_bad = self.db.create_request(
            type_="url",
            status="ok",
            correlation_id="bad",
            chat_id=1,
            user_id=1,
            input_url="https://example.com/bad",
            normalized_url="https://example.com/bad",
            route_version=1,
        )
        self.db.insert_summary(
            request_id=rid_bad,
            lang="en",
            json_payload=bad_summary,
        )

        rid_empty_links = self.db.create_request(
            type_="url",
            status="ok",
            correlation_id="empty",
            chat_id=1,
            user_id=1,
            input_url="https://example.com/empty",
            normalized_url="https://example.com/empty",
            route_version=1,
        )
        self.db.insert_summary(
            request_id=rid_empty_links,
            lang="en",
            json_payload=base_summary,
        )
        self.db.insert_crawl_result(
            request_id=rid_empty_links,
            source_url="https://example.com/empty",
            endpoint="/v1/scrape",
            http_status=200,
            status="ok",
            options_json={},
            correlation_id="fc-empty",
            content_markdown="# md",
            content_html=None,
            structured_json={},
            metadata_json={},
            links_json=[],
            screenshots_paths_json=None,
            firecrawl_success=True,
            firecrawl_error_code=None,
            firecrawl_error_message=None,
            firecrawl_details_json=None,
            raw_response_json=None,
            latency_ms=100,
            error_text=None,
        )

        rid_missing = self.db.create_request(
            type_="url",
            status="pending",
            correlation_id="missing",
            chat_id=1,
            user_id=1,
            input_url="https://example.com/missing",
            normalized_url="https://example.com/missing",
            route_version=1,
        )

        verification = self.db.verify_processing_integrity()

        self.assertIn("overview", verification)
        posts = verification.get("posts")
        self.assertIsInstance(posts, dict)
        overview = verification.get("overview")
        self.assertIsInstance(overview, dict)
        self.assertEqual(posts.get("checked"), 4)
        self.assertEqual(posts.get("with_summary"), 3)
        self.assertEqual(overview.get("total_requests"), 4)
        self.assertEqual(overview.get("total_summaries"), 3)

        missing_summary = posts.get("missing_summary") or []
        self.assertEqual(len(missing_summary), 1)
        self.assertEqual(missing_summary[0]["request_id"], rid_missing)

        missing_fields = posts.get("missing_fields") or []
        bad_entries = [entry for entry in missing_fields if entry.get("request_id") == rid_bad]
        self.assertTrue(bad_entries)
        bad_missing = bad_entries[0].get("missing") or []
        self.assertIn("summary_250", bad_missing)
        self.assertIn("summary_1000", bad_missing)
        self.assertIn("tldr", bad_missing)
        self.assertIn("metadata", bad_missing)

        links_info = posts.get("links") or {}
        self.assertEqual(links_info.get("total_links"), 2)
        self.assertEqual(links_info.get("posts_with_links"), 4)
        missing_links = links_info.get("missing_data") or []
        missing_map = {entry.get("request_id"): entry for entry in missing_links}
        self.assertIn(rid_bad, missing_map)
        self.assertEqual(missing_map[rid_bad].get("reason"), "absent_links_json")
        self.assertIn(rid_missing, missing_map)
        self.assertEqual(missing_map[rid_missing].get("reason"), "absent_links_json")

        reprocess_entries = posts.get("reprocess") or []
        self.assertEqual(len(reprocess_entries), 2)
        reprocess_map = {
            entry.get("request_id"): set(entry.get("reasons") or []) for entry in reprocess_entries
        }
        self.assertIn(rid_bad, reprocess_map)
        self.assertIn("missing_fields", reprocess_map[rid_bad])
        self.assertIn("missing_links", reprocess_map[rid_bad])
        self.assertIn(rid_missing, reprocess_map)
        self.assertIn("missing_summary", reprocess_map[rid_missing])
        self.assertIn("missing_links", reprocess_map[rid_missing])
        self.assertNotIn(rid_empty_links, reprocess_map)

    def test_insert_telegram_message_handles_duplicate_request(self):
        rid = self.db.create_request(
            type_="url",
            status="pending",
            correlation_id="cid-telegram",
            chat_id=1,
            user_id=2,
            input_url="https://example.org",
            normalized_url="https://example.org",
            dedupe_hash="telegram-dup",
            route_version=1,
        )

        mid1 = self.db.insert_telegram_message(
            request_id=rid,
            message_id=10,
            chat_id=1,
            date_ts=1700000000,
            text_full="hello",
            entities_json=[{"type": "bold"}],
            media_type="photo",
            media_file_ids_json=["file_a"],
            forward_from_chat_id=None,
            forward_from_chat_type=None,
            forward_from_chat_title=None,
            forward_from_message_id=None,
            forward_date_ts=None,
            telegram_raw_json={"k": "v"},
        )

        mid2 = self.db.insert_telegram_message(
            request_id=rid,
            message_id=10,
            chat_id=1,
            date_ts=1700000000,
            text_full="hello",
            entities_json=[{"type": "bold"}],
            media_type="video",
            media_file_ids_json=["file_b"],
            forward_from_chat_id=None,
            forward_from_chat_type=None,
            forward_from_chat_title=None,
            forward_from_message_id=None,
            forward_date_ts=None,
            telegram_raw_json={"k": "v"},
        )

        self.assertEqual(mid1, mid2)

        row = self.db.fetchone("SELECT * FROM telegram_messages WHERE request_id = ?", (rid,))
        self.assertIsNotNone(row)
        # The original payload should remain intact
        self.assertEqual(row["media_type"], "photo")
        self.assertEqual(json.loads(row["media_file_ids_json"]), ["file_a"])


if __name__ == "__main__":
    unittest.main()
