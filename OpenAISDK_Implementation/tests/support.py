"""Shared test helpers for deterministic settings and principal creation."""

from __future__ import annotations

from app.core.config import (
    AppSettings,
    AuditSettings,
    AuthorizationSettings,
    AuthSettings,
    OidcSettings,
    TrustedHeaderSettings,
)
from app.security.models import UserPrincipal


def build_test_settings(
    *,
    auth_mode: str = "disabled",
    authorization_enabled: bool = False,
    execute_task_roles: tuple[str, ...] = ("admin", "user"),
    admin_groups: tuple[str, ...] = (),
    user_groups: tuple[str, ...] = (),
    readonly_groups: tuple[str, ...] = (),
    audit_enabled: bool = False,
    codex_model: str | None = None,
    codex_bin: str | None = None,
    codex_project_source: str | None = None,
    codex_sessions_base_path: str | None = None,
    environment: str = "test",
    enable_docs: bool = True,
    trusted_proxy_ips: tuple[str, ...] = (),
    oidc_issuer: str | None = "https://issuer.example.com",
    oidc_audience: str | None = "api://test",
    oidc_jwks_url: str | None = "https://issuer.example.com/jwks",
) -> AppSettings:
    """Create deterministic application settings for tests."""
    return AppSettings(
        active_profile="test",
        config_file_path="/tmp/test-app.toml",
        app_name="Test API",
        app_description="Test description",
        app_version="1.0.0",
        environment=environment,
        api_prefix="/api/v1",
        docs_url="/docs" if enable_docs else None,
        redoc_url="/redoc" if enable_docs else None,
        openapi_url="/openapi.json" if enable_docs else None,
        log_level="INFO",
        cors_allowed_origins=("http://localhost",),
        codex_bin=codex_bin,
        codex_model=codex_model,
        codex_project_source=codex_project_source,
        codex_sessions_base_path=codex_sessions_base_path,
        auth=AuthSettings(
            mode=auth_mode,
            oidc=OidcSettings(
                issuer=oidc_issuer,
                audience=oidc_audience,
                jwks_url=oidc_jwks_url,
                algorithms=("RS256",),
                required_claims=("sub",),
                subject_claim="sub",
                username_claim="preferred_username",
                email_claim="email",
                groups_claim="groups",
                roles_claim="roles",
                tenant_claim="tid",
                clock_skew_seconds=60,
            ),
            trusted_header=TrustedHeaderSettings(
                user_header="X-Authenticated-User",
                email_header="X-Authenticated-Email",
                groups_header="X-Authenticated-Groups",
                roles_header="X-Authenticated-Roles",
                group_separator=";",
                trusted_proxy_ips=trusted_proxy_ips,
            ),
            authorization=AuthorizationSettings(
                enabled=authorization_enabled,
                execute_task_roles=execute_task_roles,
                admin_groups=admin_groups,
                user_groups=user_groups,
                readonly_groups=readonly_groups,
            ),
        ),
        audit=AuditSettings(enabled=audit_enabled),
    )


def build_test_principal(
    *,
    subject: str = "local-development",
    username: str = "local-development",
    auth_mode: str = "disabled",
    roles: tuple[str, ...] = ("admin",),
    groups: tuple[str, ...] = (),
    email: str | None = None,
) -> UserPrincipal:
    """Create a deterministic principal for service and endpoint tests."""
    return UserPrincipal(
        subject=subject,
        username=username,
        auth_mode=auth_mode,
        roles=roles,
        groups=groups,
        email=email,
    )
