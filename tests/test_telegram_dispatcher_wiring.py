from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.di.telegram import _build_command_dispatcher_deps
from app.di.types import TelegramRepositories
from tests.conftest import make_test_app_config


def test_command_dispatcher_routes_preserve_expected_precedence_order() -> None:
    cfg = make_test_app_config()
    repositories = TelegramRepositories(
        user_repository=MagicMock(),
        summary_repository=MagicMock(),
        request_repository=MagicMock(),
        llm_repository=MagicMock(),
        audit_log_repository=MagicMock(),
        batch_session_repository=MagicMock(),
    )
    application_services = SimpleNamespace(
        unread_summaries=MagicMock(),
        mark_summary_as_read=MagicMock(),
        event_bus=MagicMock(),
        search_topics=MagicMock(),
    )

    deps = _build_command_dispatcher_deps(
        cfg=cfg,
        db=MagicMock(),
        response_formatter=MagicMock(),
        audit_func=MagicMock(),
        url_processor=MagicMock(),
        url_handler=MagicMock(),
        topic_searcher=MagicMock(),
        local_searcher=MagicMock(),
        task_manager=MagicMock(),
        hybrid_search=MagicMock(),
        verbosity_resolver=MagicMock(),
        application_services=application_services,
        repositories=repositories,
        tts_service_factory=lambda: MagicMock(),
    )

    assert [route.prefix for route in deps.routes.pre_alias_uid] == [
        "/start",
        "/help",
        "/dbinfo",
        "/dbverify",
        "/clearcache",
    ]
    assert [route.prefix for route in deps.routes.pre_alias_text] == ["/admin"]
    assert [route.aliases for route in deps.routes.local_search_aliases] == [
        ("/finddb", "/findlocal")
    ]
    assert [route.aliases for route in deps.routes.online_search_aliases] == [
        ("/findweb", "/findonline", "/find")
    ]
    assert [route.prefix for route in deps.routes.pre_summarize_text] == ["/summarize_all"]
    assert deps.routes.summarize_prefix == "/summarize"
    assert [route.prefix for route in deps.routes.post_summarize_uid] == ["/cancel"]
    assert [route.prefix for route in deps.routes.post_summarize_text] == [
        "/untag",
        "/tags",
        "/tag",
        "/unread",
        "/read",
        "/search",
        "/listen",
        "/cdigest",
        "/digest",
        "/channels",
        "/subscribe",
        "/unsubscribe",
        "/init_session",
        "/settings",
        "/rules",
        "/export",
        "/backups",
        "/backup",
    ]
    assert [route.prefix for route in deps.routes.tail_uid] == ["/debug"]
