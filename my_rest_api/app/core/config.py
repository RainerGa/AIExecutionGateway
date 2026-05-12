"""Centralized application settings loaded from config profiles and environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    import tomli as tomllib

from app import __version__

AUTH_MODES = {"disabled", "trusted_header", "oidc_jwt"}


def _project_root() -> Path:
    """Return the repository-local project root that contains the config directory."""
    return Path(__file__).resolve().parents[2]


def _default_config_file_path() -> Path:
    """Return the default config file path used when no override is provided."""
    return _project_root() / "config" / "app.toml"


def _parse_csv(value: str | None) -> tuple[str, ...]:
    """Convert a comma-separated environment value into a normalized tuple."""
    if not value:
        return ()

    items = [item.strip() for item in value.split(",")]
    return tuple(item for item in items if item)


def _to_string_tuple(value: object, *, fallback: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Normalize strings or lists of strings into an immutable tuple representation."""
    if value is None:
        return fallback

    if isinstance(value, str):
        return _parse_csv(value)

    if isinstance(value, (list, tuple)):
        normalized = []
        for item in value:
            text = str(item).strip()
            if text:
                normalized.append(text)
        return tuple(normalized)

    return fallback


def _parse_bool(value: object, *, default: bool) -> bool:
    """Parse booleans from TOML-native or environment-style truthy values."""
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False

    return default


def _deep_merge(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    """Merge nested dictionaries while replacing scalar and list values."""
    merged = dict(base)
    for key, value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(base_value, value)
        else:
            merged[key] = value
    return merged


@dataclass(frozen=True, slots=True)
class OidcSettings:
    """OIDC token-validation settings for enterprise SSO integration."""

    issuer: str | None
    audience: str | None
    jwks_url: str | None
    algorithms: tuple[str, ...]
    required_claims: tuple[str, ...]
    subject_claim: str
    username_claim: str
    email_claim: str
    groups_claim: str
    roles_claim: str
    tenant_claim: str
    clock_skew_seconds: int


@dataclass(frozen=True, slots=True)
class TrustedHeaderSettings:
    """Header names and trust boundaries for reverse-proxy authentication."""

    user_header: str
    email_header: str
    groups_header: str
    roles_header: str
    group_separator: str
    trusted_proxy_ips: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AuthorizationSettings:
    """Role-mapping and access-control settings."""

    enabled: bool
    execute_task_roles: tuple[str, ...]
    admin_groups: tuple[str, ...]
    user_groups: tuple[str, ...]
    readonly_groups: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AuthSettings:
    """Top-level authentication configuration for the API."""

    mode: str
    oidc: OidcSettings
    trusted_header: TrustedHeaderSettings
    authorization: AuthorizationSettings


@dataclass(frozen=True, slots=True)
class AuditSettings:
    """Feature flags for audit-related runtime behavior."""

    enabled: bool


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Immutable runtime configuration for the REST API service."""

    active_profile: str
    config_file_path: str
    app_name: str
    app_description: str
    app_version: str
    environment: str
    api_prefix: str
    docs_url: str | None
    redoc_url: str | None
    openapi_url: str | None
    log_level: str
    cors_allowed_origins: tuple[str, ...]
    codex_bin: str | None
    codex_model: str | None
    codex_project_source: str | None
    codex_sessions_base_path: str | None
    auth: AuthSettings
    audit: AuditSettings


def _default_config_document() -> dict[str, object]:
    """Provide in-code defaults that are safe for local development."""
    return {
        "active_profile": "home",
        "defaults": {
            "app_name": "OpenAI Codex Task Execution API",
            "app_description": (
                "Enterprise-oriented REST API for orchestrating Codex task execution "
                "through a versioned FastAPI service."
            ),
            "environment": "development",
            "api_prefix": "/api/v1",
            "enable_docs": True,
            "log_level": "INFO",
            "cors_allowed_origins": [
                "http://localhost",
                "http://127.0.0.1",
            ],
            "codex_bin": None,
            "codex_model": None,
            "codex_project_source": None,
            "codex_sessions_base_path": None,
            "auth": {
                "mode": "disabled",
            },
            "authorization": {
                "enabled": False,
                "execute_task_roles": ["admin", "user"],
                "admin_groups": [],
                "user_groups": [],
                "readonly_groups": [],
            },
            "audit": {
                "enabled": False,
            },
            "oidc": {
                "issuer": None,
                "audience": None,
                "jwks_url": None,
                "algorithms": ["RS256"],
                "required_claims": ["sub"],
                "subject_claim": "sub",
                "username_claim": "preferred_username",
                "email_claim": "email",
                "groups_claim": "groups",
                "roles_claim": "roles",
                "tenant_claim": "tid",
                "clock_skew_seconds": 60,
            },
            "trusted_header": {
                "user_header": "X-Authenticated-User",
                "email_header": "X-Authenticated-Email",
                "groups_header": "X-Authenticated-Groups",
                "roles_header": "X-Authenticated-Roles",
                "group_separator": ";",
                "trusted_proxy_ips": [],
            },
        },
        "profiles": {},
    }


def _resolve_config_file_path() -> Path:
    """Resolve the configuration file path from environment or repository defaults."""
    configured_path = (os.getenv("APP_CONFIG_FILE") or "").strip()
    if not configured_path:
        return _default_config_file_path()

    path = Path(configured_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _load_config_document(path: Path) -> dict[str, object]:
    """Load the TOML document when present, or return an empty structure."""
    if not path.exists():
        if os.getenv("APP_CONFIG_FILE"):
            raise FileNotFoundError(f"Configured APP_CONFIG_FILE does not exist: {path}")
        return {}

    with path.open("rb") as file_handle:
        return tomllib.load(file_handle)


def _apply_env_overrides(config: dict[str, object]) -> dict[str, object]:
    """Apply environment-based overrides after profile resolution."""
    overridden = dict(config)
    auth_block = dict(overridden.get("auth", {}))
    authorization_block = dict(overridden.get("authorization", {}))
    audit_block = dict(overridden.get("audit", {}))
    oidc_block = dict(overridden.get("oidc", {}))
    trusted_header_block = dict(overridden.get("trusted_header", {}))

    if os.getenv("APP_ENV"):
        overridden["environment"] = os.getenv("APP_ENV")
    if os.getenv("API_PREFIX"):
        overridden["api_prefix"] = os.getenv("API_PREFIX")
    if os.getenv("ENABLE_DOCS"):
        overridden["enable_docs"] = os.getenv("ENABLE_DOCS")
    if os.getenv("LOG_LEVEL"):
        overridden["log_level"] = os.getenv("LOG_LEVEL")
    if os.getenv("CORS_ALLOWED_ORIGINS"):
        overridden["cors_allowed_origins"] = _parse_csv(os.getenv("CORS_ALLOWED_ORIGINS"))
    if os.getenv("CODEX_BIN"):
        overridden["codex_bin"] = os.getenv("CODEX_BIN")
    if os.getenv("CODEX_MODEL"):
        overridden["codex_model"] = os.getenv("CODEX_MODEL")
    if os.getenv("CODEX_PROJECT_SOURCE"):
        overridden["codex_project_source"] = os.getenv("CODEX_PROJECT_SOURCE")
    if os.getenv("CODEX_SESSIONS_BASE_PATH"):
        overridden["codex_sessions_base_path"] = os.getenv("CODEX_SESSIONS_BASE_PATH")
    if os.getenv("AUTH_MODE"):
        auth_block["mode"] = os.getenv("AUTH_MODE")
    if os.getenv("AUTHORIZATION_ENABLED"):
        authorization_block["enabled"] = os.getenv("AUTHORIZATION_ENABLED")
    if os.getenv("AUDIT_ENABLED"):
        audit_block["enabled"] = os.getenv("AUDIT_ENABLED")
    if os.getenv("OIDC_ISSUER"):
        oidc_block["issuer"] = os.getenv("OIDC_ISSUER")
    if os.getenv("OIDC_AUDIENCE"):
        oidc_block["audience"] = os.getenv("OIDC_AUDIENCE")
    if os.getenv("OIDC_JWKS_URL"):
        oidc_block["jwks_url"] = os.getenv("OIDC_JWKS_URL")
    if os.getenv("TRUSTED_HEADER_USER_HEADER"):
        trusted_header_block["user_header"] = os.getenv("TRUSTED_HEADER_USER_HEADER")
    if os.getenv("TRUSTED_HEADER_EMAIL_HEADER"):
        trusted_header_block["email_header"] = os.getenv("TRUSTED_HEADER_EMAIL_HEADER")
    if os.getenv("TRUSTED_HEADER_GROUPS_HEADER"):
        trusted_header_block["groups_header"] = os.getenv("TRUSTED_HEADER_GROUPS_HEADER")
    if os.getenv("TRUSTED_HEADER_ROLES_HEADER"):
        trusted_header_block["roles_header"] = os.getenv("TRUSTED_HEADER_ROLES_HEADER")
    if os.getenv("TRUSTED_PROXY_IPS"):
        trusted_header_block["trusted_proxy_ips"] = _parse_csv(os.getenv("TRUSTED_PROXY_IPS"))

    overridden["auth"] = auth_block
    overridden["authorization"] = authorization_block
    overridden["audit"] = audit_block
    overridden["oidc"] = oidc_block
    overridden["trusted_header"] = trusted_header_block
    return overridden


def _resolve_profile_document() -> tuple[Path, str, dict[str, object]]:
    """Resolve the active profile and return its merged configuration."""
    config_path = _resolve_config_file_path()
    default_document = _default_config_document()
    loaded_document = _load_config_document(config_path)

    defaults_block = _deep_merge(
        default_document["defaults"],
        loaded_document.get("defaults", {}),
    )
    active_profile = (
        (os.getenv("APP_ACTIVE_PROFILE") or "").strip()
        or str(loaded_document.get("active_profile") or default_document["active_profile"])
    )
    profile_block = loaded_document.get("profiles", {}).get(active_profile, {})
    merged = _deep_merge(defaults_block, profile_block)
    merged = _apply_env_overrides(merged)
    return config_path, active_profile, merged


def _build_settings(
    config_path: Path,
    active_profile: str,
    config: dict[str, object],
) -> AppSettings:
    """Convert a merged config document into a typed settings object."""
    auth_mode = str(config.get("auth", {}).get("mode", "disabled")).strip().lower()
    if auth_mode not in AUTH_MODES:
        raise ValueError(f"Unsupported auth mode configured: {auth_mode}")

    enable_docs = _parse_bool(config.get("enable_docs"), default=True)
    authorization_config = config.get("authorization", {})
    audit_config = config.get("audit", {})
    oidc_config = config.get("oidc", {})
    trusted_header_config = config.get("trusted_header", {})

    authorization_settings = AuthorizationSettings(
        enabled=_parse_bool(authorization_config.get("enabled"), default=False),
        execute_task_roles=_to_string_tuple(
            authorization_config.get("execute_task_roles"),
            fallback=("admin", "user"),
        ),
        admin_groups=_to_string_tuple(authorization_config.get("admin_groups")),
        user_groups=_to_string_tuple(authorization_config.get("user_groups")),
        readonly_groups=_to_string_tuple(authorization_config.get("readonly_groups")),
    )

    oidc_settings = OidcSettings(
        issuer=(str(oidc_config.get("issuer")).strip() if oidc_config.get("issuer") else None),
        audience=(
            str(oidc_config.get("audience")).strip() if oidc_config.get("audience") else None
        ),
        jwks_url=(str(oidc_config.get("jwks_url")).strip() if oidc_config.get("jwks_url") else None),
        algorithms=_to_string_tuple(oidc_config.get("algorithms"), fallback=("RS256",)),
        required_claims=_to_string_tuple(oidc_config.get("required_claims"), fallback=("sub",)),
        subject_claim=str(oidc_config.get("subject_claim", "sub")).strip() or "sub",
        username_claim=(
            str(oidc_config.get("username_claim", "preferred_username")).strip()
            or "preferred_username"
        ),
        email_claim=str(oidc_config.get("email_claim", "email")).strip() or "email",
        groups_claim=str(oidc_config.get("groups_claim", "groups")).strip() or "groups",
        roles_claim=str(oidc_config.get("roles_claim", "roles")).strip() or "roles",
        tenant_claim=str(oidc_config.get("tenant_claim", "tid")).strip() or "tid",
        clock_skew_seconds=int(oidc_config.get("clock_skew_seconds", 60)),
    )

    trusted_header_settings = TrustedHeaderSettings(
        user_header=(
            str(trusted_header_config.get("user_header", "X-Authenticated-User")).strip()
            or "X-Authenticated-User"
        ),
        email_header=(
            str(trusted_header_config.get("email_header", "X-Authenticated-Email")).strip()
            or "X-Authenticated-Email"
        ),
        groups_header=(
            str(trusted_header_config.get("groups_header", "X-Authenticated-Groups")).strip()
            or "X-Authenticated-Groups"
        ),
        roles_header=(
            str(trusted_header_config.get("roles_header", "X-Authenticated-Roles")).strip()
            or "X-Authenticated-Roles"
        ),
        group_separator=(
            str(trusted_header_config.get("group_separator", ";")).strip() or ";"
        ),
        trusted_proxy_ips=_to_string_tuple(trusted_header_config.get("trusted_proxy_ips")),
    )

    return AppSettings(
        active_profile=active_profile,
        config_file_path=str(config_path),
        app_name=str(config.get("app_name", "OpenAI Codex Task Execution API")).strip()
        or "OpenAI Codex Task Execution API",
        app_description=(
            str(config.get("app_description")).strip()
            if config.get("app_description")
            else (
                "Enterprise-oriented REST API for orchestrating Codex task execution "
                "through a versioned FastAPI service."
            )
        ),
        app_version=__version__,
        environment=str(config.get("environment", "development")).strip().lower() or "development",
        api_prefix=str(config.get("api_prefix", "/api/v1")).strip() or "/api/v1",
        docs_url="/docs" if enable_docs else None,
        redoc_url="/redoc" if enable_docs else None,
        openapi_url="/openapi.json" if enable_docs else None,
        log_level=str(config.get("log_level", "INFO")).strip().upper() or "INFO",
        cors_allowed_origins=_to_string_tuple(
            config.get("cors_allowed_origins"),
            fallback=("http://localhost", "http://127.0.0.1"),
        ),
        codex_bin=(str(config.get("codex_bin")).strip() if config.get("codex_bin") else None),
        codex_model=(str(config.get("codex_model")).strip() if config.get("codex_model") else None),
        codex_project_source=(
            str(config.get("codex_project_source")).strip()
            if config.get("codex_project_source")
            else None
        ),
        codex_sessions_base_path=(
            str(config.get("codex_sessions_base_path")).strip()
            if config.get("codex_sessions_base_path")
            else None
        ),
        auth=AuthSettings(
            mode=auth_mode,
            oidc=oidc_settings,
            trusted_header=trusted_header_settings,
            authorization=authorization_settings,
        ),
        audit=AuditSettings(
            enabled=_parse_bool(audit_config.get("enabled"), default=False),
        ),
    )


@lru_cache
def get_settings() -> AppSettings:
    """Build and cache the settings object for the current process."""
    config_path, active_profile, merged_config = _resolve_profile_document()
    return _build_settings(config_path, active_profile, merged_config)
