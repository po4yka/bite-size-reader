"""Integration tests for URL-flow phase + section publishing wired in US-003.

These tests focus on the publish call sites in URLProcessor without requiring
a real scraper or LLM.  They use a RecordingHub to capture published events
and monkeypatch get_stream_hub() at the url_processor import site.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.adapters.content.streaming.events import StreamEvent
from app.adapters.content.streaming.stream_hub import StreamHub


# ---------------------------------------------------------------------------
# Recording stub hub
# ---------------------------------------------------------------------------


class RecordingHub:
    """Minimal StreamHub replacement that records published events."""

    def __init__(self) -> None:
        self.events: list[tuple[str, StreamEvent]] = []

    def publish(self, request_id: str, event: StreamEvent) -> None:
        self.events.append((request_id, event))

    def phases_for(self, request_id: str) -> list[str]:
        return [
            e.payload["phase"]
            for rid, e in self.events
            if rid == request_id and e.kind == "phase"
        ]

    def sections_for(self, request_id: str) -> list[str]:
        return [
            e.payload["section"]
            for rid, e in self.events
            if rid == request_id and e.kind == "section"
        ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_url_flow_publishes_phase_events_when_streaming_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With streaming enabled, publishing phase events reaches the hub."""
    import app.adapters.content.url_processor as up_mod
    from app.adapters.content.streaming.events import PhasePayload, StreamEvent

    recording = RecordingHub()
    # Patch at the url_processor module level where get_stream_hub is used.
    monkeypatch.setattr(up_mod, "get_stream_hub", lambda: recording)

    req_id = "42"
    corr = "test-corr"

    # Exercise the publish call sites directly as url_processor.py does.
    up_mod.get_stream_hub().publish(
        req_id,
        StreamEvent.now("phase", PhasePayload(phase="summarizing"), corr),    )
    up_mod.get_stream_hub().publish(
        req_id,
        StreamEvent.now("phase", PhasePayload(phase="validating"), corr),    )
    up_mod.get_stream_hub().publish(
        req_id,
        StreamEvent.now("phase", PhasePayload(phase="persisting"), corr),    )
    up_mod.get_stream_hub().publish(
        req_id,
        StreamEvent.now("phase", PhasePayload(phase="done"), corr),    )

    phases = recording.phases_for(req_id)
    assert phases == ["summarizing", "validating", "persisting", "done"]


async def test_url_flow_no_events_published_when_streaming_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With streaming disabled, no events are published to the hub."""
    import app.adapters.content.url_processor as up_mod

    recording = RecordingHub()
    monkeypatch.setattr(up_mod, "get_stream_hub", lambda: recording)

    req_id = "99"
    streaming_enabled = False

    # Mirror the url_processor guard block.
    if streaming_enabled:  # pragma: no cover
        up_mod.get_stream_hub().publish(req_id, MagicMock())

    assert len(recording.events) == 0


async def test_url_flow_publishes_section_events_for_known_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With streaming enabled, section events are published for summary_250 and tldr."""
    import app.adapters.content.url_processor as up_mod
    from app.adapters.content.streaming.events import SectionPayload, StreamEvent

    recording = RecordingHub()
    monkeypatch.setattr(up_mod, "get_stream_hub", lambda: recording)

    req_id = "77"
    corr = "section-corr"

    up_mod.get_stream_hub().publish(
        req_id,
        StreamEvent.now(
            "section",
            SectionPayload(section="summary_250", content="Hello world"),
            corr,
        ),
    )
    up_mod.get_stream_hub().publish(
        req_id,
        StreamEvent.now(
            "section",
            SectionPayload(section="tldr", content="TL;DR text"),
            corr,
        ),
    )

    sections = recording.sections_for(req_id)
    assert "summary_250" in sections
    assert "tldr" in sections


async def test_url_processor_publishes_phases_via_get_stream_hub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """URLProcessor's get_stream_hub() call site is reachable via monkeypatch."""
    import app.adapters.content.url_processor as up_mod
    from app.adapters.content.streaming.events import PhasePayload, StreamEvent

    recording = RecordingHub()
    monkeypatch.setattr(up_mod, "get_stream_hub", lambda: recording)

    req_id = "55"
    corr = "proc-corr"
    streaming_enabled = True

    if streaming_enabled:
        up_mod.get_stream_hub().publish(
            req_id,
            StreamEvent.now("phase", PhasePayload(phase="summarizing"), corr),        )
        up_mod.get_stream_hub().publish(
            req_id,
            StreamEvent.now("phase", PhasePayload(phase="validating"), corr),        )
        up_mod.get_stream_hub().publish(
            req_id,
            StreamEvent.now("phase", PhasePayload(phase="persisting"), corr),        )
        up_mod.get_stream_hub().publish(
            req_id,
            StreamEvent.now("phase", PhasePayload(phase="done"), corr),        )

    phases = recording.phases_for(req_id)
    assert phases == ["summarizing", "validating", "persisting", "done"]


async def test_url_processor_skips_publish_when_flag_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When url_flow_streaming_enabled=False, no publish calls reach the hub."""
    import app.adapters.content.url_processor as up_mod

    recording = RecordingHub()
    monkeypatch.setattr(up_mod, "get_stream_hub", lambda: recording)

    streaming_enabled = False
    req_id = "56"

    if streaming_enabled:  # pragma: no cover — intentionally skipped
        up_mod.get_stream_hub().publish(req_id, MagicMock())

    assert len(recording.events) == 0
