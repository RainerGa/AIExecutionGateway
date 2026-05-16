"""Tests for TOML profile loading and environment-based configuration overrides."""

from __future__ import annotations

import pytest
from pathlib import Path

from app.core.config import (
    get_settings,
    _parse_csv,
    _to_string_tuple,
    _parse_bool,
    _resolve_config_file_path,
    _build_settings,
    _default_config_document,
    _load_config_document,
)


def test_get_settings_loads_active_profile_from_toml(monkeypatch, tmp_path: Path):
    """The settings loader should honor the active profile from the config file."""
    config_file = tmp_path / "app.toml"
    config_file.write_text(
        """
active_profile = "company"

[profiles.company.auth]
mode = "trusted_header"

[profiles.company.authorization]
enabled = true
user_groups = ["Codex-Users"]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("APP_CONFIG_FILE", str(config_file))
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.active_profile == "company"
    assert settings.auth.mode == "trusted_header"
    assert settings.auth.authorization.enabled is True
    assert settings.auth.authorization.user_groups == ("Codex-Users",)


def test_get_settings_allows_environment_to_override_profile(
    monkeypatch, tmp_path: Path
):
    """Environment overrides should be able to switch profiles and auth mode."""
    config_file = tmp_path / "app.toml"
    config_file.write_text(
        """
active_profile = "company"

[profiles.home.auth]
mode = "disabled"

[profiles.company.auth]
mode = "trusted_header"
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("APP_CONFIG_FILE", str(config_file))
    monkeypatch.setenv("APP_ACTIVE_PROFILE", "home")
    monkeypatch.setenv("AUTH_MODE", "trusted_header")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.active_profile == "home"
    assert settings.auth.mode == "trusted_header"


def test_parse_csv():
    assert _parse_csv(None) == ()
    assert _parse_csv("") == ()
    assert _parse_csv("a, b, c") == ("a", "b", "c")


def test_to_string_tuple():
    assert _to_string_tuple(None) == ()
    assert _to_string_tuple(None, fallback=("x",)) == ("x",)
    assert _to_string_tuple("a, b") == ("a", "b")
    assert _to_string_tuple([" a ", "b ", "", None]) == ("a", "b", "None")
    assert _to_string_tuple(123) == ()


def test_parse_bool():
    assert _parse_bool(True, default=False) is True
    assert _parse_bool(False, default=True) is False
    assert _parse_bool("1", default=False) is True
    assert _parse_bool("true", default=False) is True
    assert _parse_bool("yes", default=False) is True
    assert _parse_bool("on", default=False) is True
    assert _parse_bool("0", default=True) is False
    assert _parse_bool("false", default=True) is False
    assert _parse_bool("no", default=True) is False
    assert _parse_bool("off", default=True) is False
    assert _parse_bool("invalid", default=True) is True


def test_resolve_config_file_path(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("APP_CONFIG_FILE", "relative.toml")
    path = _resolve_config_file_path()
    assert path == Path.cwd() / "relative.toml"

    explicit_path = tmp_path / "does_not_exist.toml"
    monkeypatch.setenv("APP_CONFIG_FILE", str(explicit_path))
    with pytest.raises(FileNotFoundError):
        _load_config_document(explicit_path)


def test_apply_env_overrides(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("API_PREFIX", "/api/v2")
    monkeypatch.setenv("ENABLE_DOCS", "0")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://test.com")
    monkeypatch.setenv("CODEX_BIN", "/bin/codex")
    monkeypatch.setenv("CODEX_MODEL", "model-x")
    monkeypatch.setenv("CODEX_PROJECT_SOURCE", "/tmp/src")
    monkeypatch.setenv("CODEX_SESSIONS_BASE_PATH", "/tmp/sessions")
    monkeypatch.setenv("AUTH_MODE", "oidc_jwt")
    monkeypatch.setenv("AUTHORIZATION_ENABLED", "true")
    monkeypatch.setenv("AUDIT_ENABLED", "true")
    monkeypatch.setenv("MONITORING_ENABLED", "true")
    monkeypatch.setenv("MONITORING_HISTORY_SIZE", "250")
    monkeypatch.setenv("MONITORING_STREAM_ENABLED", "false")
    monkeypatch.setenv("MONITORING_REFRESH_INTERVAL_MS", "5000")
    monkeypatch.setenv("OIDC_ISSUER", "https://issuer")
    monkeypatch.setenv("OIDC_AUDIENCE", "aud")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://jwks")
    monkeypatch.setenv("TRUSTED_HEADER_USER_HEADER", "X-User")
    monkeypatch.setenv("TRUSTED_HEADER_EMAIL_HEADER", "X-Email")
    monkeypatch.setenv("TRUSTED_HEADER_GROUPS_HEADER", "X-Groups")
    monkeypatch.setenv("TRUSTED_HEADER_ROLES_HEADER", "X-Roles")
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "1.2.3.4")

    get_settings.cache_clear()
    settings = get_settings()

    assert settings.environment == "production"
    assert settings.api_prefix == "/api/v2"
    assert settings.docs_url is None
    assert settings.log_level == "DEBUG"
    assert settings.cors_allowed_origins == ("http://test.com",)
    assert settings.codex_bin == "/bin/codex"
    assert settings.codex_model == "model-x"
    assert settings.codex_project_source == "/tmp/src"
    assert settings.codex_sessions_base_path == "/tmp/sessions"
    assert settings.auth.mode == "oidc_jwt"
    assert settings.auth.authorization.enabled is True
    assert settings.audit.enabled is True
    assert settings.monitoring.enabled is True
    assert settings.monitoring.history_size == 250
    assert settings.monitoring.stream_enabled is False
    assert settings.monitoring.refresh_interval_ms == 5000
    assert settings.auth.oidc.issuer == "https://issuer"
    assert settings.auth.oidc.audience == "aud"
    assert settings.auth.oidc.jwks_url == "https://jwks"
    assert settings.auth.trusted_header.user_header == "X-User"
    assert settings.auth.trusted_header.email_header == "X-Email"
    assert settings.auth.trusted_header.groups_header == "X-Groups"
    assert settings.auth.trusted_header.roles_header == "X-Roles"
    assert settings.auth.trusted_header.trusted_proxy_ips == ("1.2.3.4",)


def test_build_settings_invalid_auth_mode():
    config = _default_config_document()
    config["auth"] = {"mode": "invalid"}
    with pytest.raises(ValueError, match="Unsupported auth mode"):
        _build_settings(Path("dummy"), "test", config)


def test_default_config_document_contains_monitoring_defaults():
    config = _default_config_document()

    assert config["defaults"]["monitoring"]["enabled"] is True
    assert config["defaults"]["monitoring"]["history_size"] == 100
    assert config["defaults"]["monitoring"]["stream_enabled"] is True
    assert config["defaults"]["monitoring"]["refresh_interval_ms"] == 1000


@pytest.mark.parametrize("env_name", ["production", "prod"])
def test_build_settings_disabled_auth_in_production_raises_error(env_name: str):
    """The system must refuse to start with disabled auth in production environments."""
    config = _default_config_document()
    config["auth"] = {"mode": "disabled"}
    config["environment"] = env_name
    with pytest.raises(
        ValueError,
        match="Authentication mode 'disabled' is not permitted in a production environment",
    ):
        _build_settings(Path("dummy"), "test", config)


@pytest.mark.parametrize("env_name", ["development", "test", "staging"])
def test_build_settings_disabled_auth_in_non_production_is_allowed(env_name: str):
    """The system may start with disabled auth in non-production environments."""
    config = _default_config_document()
    config["auth"] = {"mode": "disabled"}
    config["environment"] = env_name
    settings = _build_settings(Path("dummy"), "test", config)
    assert settings.auth.mode == "disabled"
    assert settings.environment == env_name


def test_build_settings_clamps_monitoring_limits():
    config = _default_config_document()
    config["monitoring"] = {
        "enabled": True,
        "history_size": 1,
        "stream_enabled": True,
        "refresh_interval_ms": 5,
    }

    settings = _build_settings(Path("dummy"), "test", config)

    assert settings.monitoring.history_size == 10
    assert settings.monitoring.refresh_interval_ms == 250
