from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from app.cli import _runtime as cli_runtime
from app.cli import summary as summary_cli


def test_resolve_text_prefers_url_argument() -> None:
    args = Namespace(text=None, url="https://example.com")
    assert summary_cli._resolve_text(args) == "/summary https://example.com"


def test_resolve_text_rejects_conflicting_inputs() -> None:
    args = Namespace(text="/summary https://a", url="https://b")
    with pytest.raises(SystemExit, match="Specify either"):
        summary_cli._resolve_text(args)


def test_load_env_file_sets_missing_values_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "PLAIN=value\nQUOTED_SINGLE='single'\nQUOTED_DOUBLE=\"double\"\nINVALID_LINE\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("PLAIN", raising=False)
    monkeypatch.setenv("QUOTED_SINGLE", "already-set")
    monkeypatch.delenv("QUOTED_DOUBLE", raising=False)

    cli_runtime.load_env_file(env_path)

    assert Path(env_path).exists()
    assert cli_runtime.os.environ["PLAIN"] == "value"
    assert cli_runtime.os.environ["QUOTED_SINGLE"] == "already-set"
    assert cli_runtime.os.environ["QUOTED_DOUBLE"] == "double"


def test_main_returns_zero_when_run_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_run(args: Namespace) -> None:
        assert args.url == "https://example.com"

    monkeypatch.setattr(summary_cli, "run_summary_cli", _fake_run)
    rc = summary_cli.main(["--url", "https://example.com"])
    assert rc == 0


def test_main_returns_one_when_run_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom(_args: Namespace) -> None:
        msg = "boom"
        raise RuntimeError(msg)

    monkeypatch.setattr(summary_cli, "run_summary_cli", _boom)
    rc = summary_cli.main(["--url", "https://example.com"])
    assert rc == 1
