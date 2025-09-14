import json
import os
import tempfile
import unittest

from app.adapters.telegram_bot import TelegramBot
from app.config import AppConfig, FirecrawlConfig, OpenRouterConfig, RuntimeConfig, TelegramConfig
from app.db.database import Database


class _Ent:
    def __init__(self, t):
        self.type = t

    def to_dict(self):
        return {"type": self.type}


class _Obj:
    def __init__(self, file_id):
        self.file_id = file_id


class _Chat:
    id = 1


class _MsgBase:
    def __init__(self):
        self.chat = _Chat()
        self.id = 10
        self.message_id = 10
        self.date = 1710000000
        self.text = None
        self.caption = None
        self.entities = [_Ent("bold")]
        self.caption_entities = []

    def to_dict(self):  # lightweight
        return {"id": self.id, "message_id": self.message_id}


def _bot_with_tmpdb(tmp_path):
    db = Database(tmp_path)
    db.migrate()
    cfg = AppConfig(
        telegram=TelegramConfig(api_id=0, api_hash="", bot_token="", allowed_user_ids=tuple()),
        firecrawl=FirecrawlConfig(api_key="x"),
        openrouter=OpenRouterConfig(
            api_key="y", model="m", fallback_models=tuple(), http_referer=None, x_title=None
        ),
        runtime=RuntimeConfig(
            db_path=tmp_path,
            log_level="INFO",
            request_timeout_sec=5,
            preferred_lang="en",
            debug_payloads=False,
        ),
    )
    from app.adapters import telegram_bot as tbmod

    tbmod.Client = object  # avoid real client
    tbmod.filters = None
    bot = TelegramBot(cfg=cfg, db=db)
    return bot, db


class TestMediaSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "app.db")
        self.bot, self.db = _bot_with_tmpdb(self.db_path)
        self.req_id = self.db.create_request(
            type_="forward",
            status="pending",
            correlation_id=None,
            chat_id=1,
            user_id=1,
            route_version=1,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _assert_media(self, expected_type, expected_ids):
        row = self.db.fetchone(
            "SELECT media_type, media_file_ids_json FROM telegram_messages WHERE request_id = ?",
            (self.req_id,),
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["media_type"], expected_type)
        if expected_ids:
            self.assertIsNotNone(row["media_file_ids_json"])
            ids = json.loads(row["media_file_ids_json"]) if row["media_file_ids_json"] else []
            self.assertEqual(ids, expected_ids)
        else:
            self.assertIsNone(row["media_file_ids_json"])

    def test_photo_snapshot(self):
        class Msg(_MsgBase):
            def __init__(self):
                super().__init__()
                self.photo = _Obj("ph_1")

        self.bot._persist_message_snapshot(self.req_id, Msg())
        self._assert_media("photo", ["ph_1"])

    def test_video_snapshot(self):
        class Msg(_MsgBase):
            def __init__(self):
                super().__init__()
                self.video = _Obj("vid_1")

        self.bot._persist_message_snapshot(self.req_id, Msg())
        self._assert_media("video", ["vid_1"])

    def test_document_snapshot(self):
        class Msg(_MsgBase):
            def __init__(self):
                super().__init__()
                self.document = _Obj("doc_1")

        self.bot._persist_message_snapshot(self.req_id, Msg())
        self._assert_media("document", ["doc_1"])

    def test_audio_snapshot(self):
        class Msg(_MsgBase):
            def __init__(self):
                super().__init__()
                self.audio = _Obj("aud_1")

        self.bot._persist_message_snapshot(self.req_id, Msg())
        self._assert_media("audio", ["aud_1"])

    def test_voice_snapshot(self):
        class Msg(_MsgBase):
            def __init__(self):
                super().__init__()
                self.voice = _Obj("voc_1")

        self.bot._persist_message_snapshot(self.req_id, Msg())
        self._assert_media("voice", ["voc_1"])

    def test_animation_snapshot(self):
        class Msg(_MsgBase):
            def __init__(self):
                super().__init__()
                self.animation = _Obj("ani_1")

        self.bot._persist_message_snapshot(self.req_id, Msg())
        self._assert_media("animation", ["ani_1"])

    def test_sticker_snapshot(self):
        class Msg(_MsgBase):
            def __init__(self):
                super().__init__()
                self.sticker = _Obj("stk_1")

        self.bot._persist_message_snapshot(self.req_id, Msg())
        self._assert_media("sticker", ["stk_1"])

    def test_entities_merge(self):
        class Msg(_MsgBase):
            def __init__(self):
                super().__init__()
                self.text = "Hello"
                self.caption = "World"
                self.entities = [_Ent("bold")]
                self.caption_entities = [_Ent("url")]

        self.bot._persist_message_snapshot(self.req_id, Msg())
        row = self.db.fetchone(
            "SELECT entities_json FROM telegram_messages WHERE request_id = ?", (self.req_id,)
        )
        self.assertIsNotNone(row)
        ents = json.loads(row["entities_json"]) if row["entities_json"] else []
        types = {e.get("type") for e in ents}
        self.assertSetEqual(types, {"bold", "url"})

    def test_forward_snapshot(self):
        class _FwdChat:
            def __init__(self):
                self.id = 777
                self.type = "channel"
                self.title = "My Channel"

        class Msg(_MsgBase):
            def __init__(self):
                super().__init__()
                self.forward_from_chat = _FwdChat()
                self.forward_from_message_id = 555
                self.forward_date = 1700000000

        self.bot._persist_message_snapshot(self.req_id, Msg())
        row = self.db.fetchone(
            "SELECT forward_from_chat_id, forward_from_chat_type, forward_from_chat_title, forward_from_message_id, forward_date_ts FROM telegram_messages WHERE request_id = ?",
            (self.req_id,),
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["forward_from_chat_id"], 777)
        self.assertEqual(row["forward_from_chat_type"], "channel")
        self.assertEqual(row["forward_from_chat_title"], "My Channel")
        self.assertEqual(row["forward_from_message_id"], 555)
        self.assertEqual(row["forward_date_ts"], 1700000000)


if __name__ == "__main__":
    unittest.main()
