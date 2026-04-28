"""Ratatoskr CLI configuration management."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from ratatoskr_cli.exceptions import ConfigError


@dataclass
class RatatoskrConfig:
    """CLI configuration."""

    server_url: str = ""
    client_id: str = ""
    user_id: int = 0
    access_token: str = ""
    refresh_token: str = ""
    token_expires_at: str = ""  # ISO 8601


def get_config_dir() -> Path:
    """Return config directory (XDG-aware)."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "ratatoskr"


def get_config_path() -> Path:
    return get_config_dir() / "config.toml"


def load_config() -> RatatoskrConfig:
    """Load config from TOML file. Returns defaults if file doesn't exist."""
    path = get_config_path()
    if not path.exists():
        return RatatoskrConfig()

    import tomllib

    with open(path, "rb") as f:
        data = tomllib.load(f)

    server = data.get("server", {})
    auth = data.get("auth", {})

    return RatatoskrConfig(
        server_url=server.get("url", ""),
        client_id=auth.get("client_id", ""),
        user_id=auth.get("user_id", 0),
        access_token=auth.get("access_token", ""),
        refresh_token=auth.get("refresh_token", ""),
        token_expires_at=auth.get("token_expires_at", ""),
    )


def _serialize_config_toml(data: dict[str, dict[str, object]]) -> str:
    lines: list[str] = []
    for section, values in data.items():
        lines.append(f"[{section}]")
        for key, value in values.items():
            if isinstance(value, str):
                escaped = value.replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'{key} = "{escaped}"')
            else:
                lines.append(f"{key} = {value}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def save_config(config: RatatoskrConfig) -> None:
    """Save config to TOML file with secure permissions."""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    path = get_config_path()
    data: dict[str, dict[str, object]] = {
        "server": {"url": config.server_url},
        "auth": {
            "client_id": config.client_id,
            "user_id": config.user_id,
            "access_token": config.access_token,
            "refresh_token": config.refresh_token,
            "token_expires_at": config.token_expires_at,
        },
    }

    with open(path, "wb") as f:
        try:
            import tomli_w
        except ModuleNotFoundError:
            f.write(_serialize_config_toml(data).encode("utf-8"))
        else:
            tomli_w.dump(data, f)

    # Secure file permissions (owner read/write only)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def require_config() -> RatatoskrConfig:
    """Load config and validate it has required fields."""
    config = load_config()
    if not config.server_url:
        raise ConfigError("Server URL not configured. Run: ratatoskr config")
    return config
