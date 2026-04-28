import os
from unittest.mock import patch

from ratatoskr_cli.config import RatatoskrConfig, get_config_dir, load_config, save_config


class TestConfig:
    def test_default_config(self, tmp_path):
        """Empty config file yields defaults."""
        with patch("ratatoskr_cli.config.get_config_dir", return_value=tmp_path):
            cfg = load_config()
            assert cfg.server_url == ""
            assert cfg.access_token == ""

    def test_save_and_load_roundtrip(self, tmp_path):
        """Config survives save -> load roundtrip."""
        with patch("ratatoskr_cli.config.get_config_dir", return_value=tmp_path):
            cfg = RatatoskrConfig(
                server_url="https://ratatoskr.example.com",
                client_id="test-cli",
                user_id=123,
                access_token="token123",
                refresh_token="refresh456",
                token_expires_at="2025-12-31T00:00:00+00:00",
            )
            save_config(cfg)
            loaded = load_config()
            assert loaded.server_url == "https://ratatoskr.example.com"
            assert loaded.client_id == "test-cli"
            assert loaded.user_id == 123
            assert loaded.access_token == "token123"

    def test_file_permissions(self, tmp_path):
        """Config file should have 0600 permissions."""
        with patch("ratatoskr_cli.config.get_config_dir", return_value=tmp_path):
            save_config(RatatoskrConfig(server_url="https://test.com"))
            config_file = tmp_path / "config.toml"
            mode = oct(os.stat(config_file).st_mode & 0o777)
            assert mode == "0o600"

    def test_xdg_config_home(self, tmp_path):
        """get_config_dir respects XDG_CONFIG_HOME."""
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path)}):
            assert get_config_dir() == tmp_path / "ratatoskr"
