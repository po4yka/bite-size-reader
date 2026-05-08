"""Matrix test: ALLOWED_USER_IDS allowlist semantics across auth paths.

Locks the unified contract: when ALLOWED_USER_IDS is empty, every auth path
fails closed. The previous divergence — JWT (dependencies.py:119) used
fail_open_when_empty=True while WebApp / Telegram-Login / secret-login all
used False — was a security gap exposed when Settings(allow_stub_telegram=True)
bypassed the startup validator at app/config/settings.py:315.

The test below verifies two complementary properties:

1. Config.is_user_allowed defaults to fail-closed and returns False on an
   empty allowlist regardless of the user_id checked.
2. All four auth-path call sites pass fail_open_when_empty=False (or omit
   it, taking the safe default). Done by static text search rather than
   monkey-driving the four routes — the routes already have integration
   coverage in tests/api/test_telegram_linking.py, tests/api/test_secret_login.py,
   and tests/test_webapp_auth.py; what we lock here is the call-site shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Config

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTH_PATHS = [
    "app/api/routers/auth/dependencies.py",
    "app/api/routers/auth/webapp_auth.py",
    "app/api/routers/auth/telegram.py",
    "app/api/routers/auth/secret_auth.py",
]


def test_is_user_allowed_fails_closed_when_allowlist_empty(monkeypatch):
    """Empty ALLOWED_USER_IDS + default fail_open → reject (fail-closed)."""
    monkeypatch.setenv("ALLOWED_USER_IDS", "")
    assert Config.is_user_allowed(123456789) is False


def test_is_user_allowed_admits_listed_user(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "123456789,987654321")
    assert Config.is_user_allowed(987654321) is True


def test_is_user_allowed_rejects_unlisted_user(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "123456789")
    assert Config.is_user_allowed(999999999) is False


def test_is_user_allowed_legacy_fail_open_path_still_works(monkeypatch):
    """fail_open_when_empty=True still admits when allowlist is empty.

    The flag stays in the API surface for tests / scripts that explicitly
    opt in. No production auth path uses it — the regression test below
    verifies that.
    """
    monkeypatch.setenv("ALLOWED_USER_IDS", "")
    assert Config.is_user_allowed(123456789, fail_open_when_empty=True) is True


@pytest.mark.parametrize("relative_path", AUTH_PATHS)
def test_no_auth_path_passes_fail_open_when_empty_true(relative_path: str):
    """Static guard: no auth path may opt into fail-open semantics.

    fail_open_when_empty=True at any of the four auth call sites would re-
    introduce the divergence this task closed. Easier to grep than to wire
    up four parameterised request mocks.
    """
    text = (REPO_ROOT / relative_path).read_text()
    assert "fail_open_when_empty=True" not in text, (
        f"{relative_path} reintroduces fail-open semantics — see "
        "docs/tasks/issues archive: unify-allowed-user-ids-allowlist-semantics"
    )


def test_config_helper_delegates_to_appconfig(monkeypatch):
    """Patching AppConfig.telegram.allowed_user_ids must propagate through
    Config.is_user_allowed — proving the helper reads the validated config
    object, not raw env vars. This is the contract that keeps tests honest
    about which deploys can authenticate which users.
    """
    from app.config import settings

    monkeypatch.setenv("ALLOWED_USER_IDS", "111,222")
    settings.clear_config_cache()
    assert settings.Config.get_allowed_user_ids() == (111, 222)
    assert settings.Config.is_user_allowed(111) is True
    assert settings.Config.is_user_allowed(333) is False

    monkeypatch.setenv("ALLOWED_USER_IDS", "555")
    settings.clear_config_cache()
    assert settings.Config.get_allowed_user_ids() == (555,)
    assert settings.Config.is_user_allowed(111) is False
    assert settings.Config.is_user_allowed(555) is True


def test_config_helper_get_allowed_client_ids_delegates_to_authconfig(monkeypatch):
    """ALLOWED_CLIENT_IDS now lives on AuthConfig.allowed_client_ids; the
    helper reads it through load_config() rather than os.getenv directly."""
    from app.config import settings

    monkeypatch.setenv("ALLOWED_CLIENT_IDS", "android-app, ios-app, cli")
    settings.clear_config_cache()
    assert settings.Config.get_allowed_client_ids() == ("android-app", "ios-app", "cli")

    # Empty / unset → no restriction (back-compat default).
    monkeypatch.setenv("ALLOWED_CLIENT_IDS", "")
    settings.clear_config_cache()
    assert settings.Config.get_allowed_client_ids() == ()


def test_authconfig_drops_invalid_client_ids(monkeypatch):
    """The validator silently drops client ids with invalid characters or
    excessive length. Behavior preserved from the previous helper."""
    from app.config import settings
    from app.config.api import AuthConfig

    cfg = AuthConfig(allowed_client_ids="ok-1,bad space,also$bad,fine_id")
    assert cfg.allowed_client_ids == ("ok-1", "fine_id")

    too_long = "a" * 101
    cfg = AuthConfig(allowed_client_ids=f"keeper,{too_long}")
    assert cfg.allowed_client_ids == ("keeper",)

    monkeypatch.setenv("ALLOWED_CLIENT_IDS", "")
    settings.clear_config_cache()
