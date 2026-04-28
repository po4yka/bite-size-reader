"""Tests for CLI commands using Click's test runner."""

import json
from unittest.mock import MagicMock, patch

from ratatoskr_cli.main import cli
from click.testing import CliRunner


class TestCLIHelp:
    def test_main_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "aggregate" in result.output
        assert "aggregation" in result.output
        assert "save" in result.output
        assert "list" in result.output
        assert "search" in result.output
        assert "tags" in result.output
        assert "collections" in result.output

    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_save_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["save", "--help"])
        assert result.exit_code == 0
        assert "--tag" in result.output
        assert "--summarize" in result.output

    def test_save_requires_url(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["save"])
        assert result.exit_code != 0

    def test_aggregate_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["aggregate", "--help"])
        assert result.exit_code == 0
        assert "--file" in result.output
        assert "--lang" in result.output
        assert "--hint" in result.output

    def test_aggregation_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["aggregation", "--help"])
        assert result.exit_code == 0
        assert "get" in result.output
        assert "list" in result.output

    def test_list_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--help"])
        assert result.exit_code == 0
        assert "--limit" in result.output
        assert "--unread" in result.output
        assert "--favorites" in result.output

    def test_search_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "--help"])
        assert result.exit_code == 0
        assert "--lang" in result.output

    def test_tags_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["tags", "--help"])
        assert result.exit_code == 0
        assert "create" in result.output
        assert "delete" in result.output

    def test_collections_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["collections", "--help"])
        assert result.exit_code == 0
        assert "create" in result.output
        assert "add" in result.output

    def test_export_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["export", "--help"])
        assert result.exit_code == 0
        assert "--format" in result.output

    def test_admin_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "--help"])
        assert result.exit_code == 0
        assert "users" in result.output
        assert "health" in result.output

    def test_config_prompts_for_url(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["config"], input="https://test.com\n")
        assert result.exit_code == 0


class TestAggregationCommands:
    def test_aggregate_uses_file_and_hints(self, tmp_path):
        source_file = tmp_path / "sources.txt"
        source_file.write_text(
            "https://one.example\n# comment\nhttps://two.example\n", encoding="utf-8"
        )

        client = MagicMock()
        client.create_aggregation_bundle.return_value = {
            "session": {"id": 7, "status": "processing"},
            "items": [],
            "aggregation": None,
        }

        runner = CliRunner()
        with patch("ratatoskr_cli.commands.aggregation.get_client", return_value=client):
            result = runner.invoke(
                cli,
                [
                    "aggregate",
                    "--file",
                    str(source_file),
                    "--lang",
                    "en",
                    "--hint",
                    "x_post",
                    "--hint",
                    "youtube_video",
                ],
            )

        assert result.exit_code == 0
        client.create_aggregation_bundle.assert_called_once_with(
            [
                {"type": "url", "url": "https://one.example", "source_kind_hint": "x_post"},
                {
                    "type": "url",
                    "url": "https://two.example",
                    "source_kind_hint": "youtube_video",
                },
            ],
            lang_preference="en",
        )

    def test_aggregate_honors_global_json(self):
        client = MagicMock()
        client.create_aggregation_bundle.return_value = {
            "session": {"id": 9, "status": "completed"},
            "items": [],
            "aggregation": {"tldr": "Short"},
        }

        runner = CliRunner()
        with patch("ratatoskr_cli.commands.aggregation.get_client", return_value=client):
            result = runner.invoke(cli, ["--json", "aggregate", "https://example.com"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["session"]["id"] == 9
        assert parsed["aggregation"]["tldr"] == "Short"

    def test_aggregate_rejects_missing_urls(self):
        runner = CliRunner()
        with patch("ratatoskr_cli.commands.aggregation.get_client", return_value=MagicMock()):
            result = runner.invoke(cli, ["aggregate"])

        assert result.exit_code != 0
