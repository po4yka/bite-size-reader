"""Tests for CLI commands using Click's test runner."""

from bsr_cli.main import cli
from click.testing import CliRunner


class TestCLIHelp:
    def test_main_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
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
