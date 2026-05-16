"""Unit tests for profile-driven authentication and authorization behavior."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from starlette.requests import Request

from app.core.exceptions import AuthenticationRequiredError, AuthorizationDeniedError
from app.security.authentication import AuthenticationService
from tests.support import build_test_settings


def build_request(
    headers: dict[str, str] | None = None,
    *,
    client_host: str = "127.0.0.1",
) -> Request:
    """Create a minimal Starlette request object for auth-service unit tests."""
    normalized_headers = []
    for key, value in (headers or {}).items():
        normalized_headers.append(
            (key.lower().encode("latin-1"), value.encode("latin-1"))
        )

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/execute_task",
        "raw_path": b"/api/v1/execute_task",
        "query_string": b"",
        "headers": normalized_headers,
        "client": (client_host, 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_disabled_auth_returns_local_development_principal():
    """The home profile should yield a deterministic local principal."""
    service = AuthenticationService(build_test_settings(auth_mode="disabled"))

    principal = service.resolve_principal(build_request())

    assert principal is not None
    assert principal.subject == "local-development"
    assert service.require_execute_task_access(principal).subject == "local-development"


def test_trusted_header_mode_requires_identity_header():
    """Trusted-header mode should require an upstream-authenticated user."""
    service = AuthenticationService(build_test_settings(auth_mode="trusted_header"))

    principal = service.resolve_principal(build_request())

    with pytest.raises(AuthenticationRequiredError):
        service.require_execute_task_access(principal)


def test_trusted_header_mode_maps_user_group_to_user_role():
    """Trusted-header mode should translate configured groups into application roles."""
    service = AuthenticationService(
        build_test_settings(
            auth_mode="trusted_header",
            authorization_enabled=True,
            user_groups=("Codex-Users",),
        )
    )

    principal = service.resolve_principal(
        build_request(
            headers={
                "X-Authenticated-User": "alice",
                "X-Authenticated-Groups": "Codex-Users",
            }
        )
    )

    assert principal is not None
    assert principal.subject == "alice"
    assert principal.roles == ("user",)
    assert service.require_execute_task_access(principal).subject == "alice"


def test_trusted_header_mode_denies_readonly_role_for_execution():
    """Trusted-header mode should deny execution when only readonly access is mapped."""
    service = AuthenticationService(
        build_test_settings(
            auth_mode="trusted_header",
            authorization_enabled=True,
            readonly_groups=("Codex-Readonly",),
        )
    )

    principal = service.resolve_principal(
        build_request(
            headers={
                "X-Authenticated-User": "bob",
                "X-Authenticated-Groups": "Codex-Readonly",
            }
        )
    )

    with pytest.raises(AuthorizationDeniedError):
        service.require_execute_task_access(principal)


def test_trusted_header_mode_rejects_untrusted_proxy_source():
    """Trusted headers should only be accepted from configured proxy addresses."""
    service = AuthenticationService(
        build_test_settings(
            auth_mode="trusted_header",
            trusted_proxy_ips=("10.0.0.10",),
        )
    )

    with pytest.raises(Exception) as exc_info:
        service.resolve_principal(
            build_request(
                headers={"X-Authenticated-User": "alice"},
                client_host="10.0.0.99",
            )
        )

    assert "untrusted source" in str(exc_info.value)


def test_oidc_mode_accepts_bearer_token_when_claims_map_to_user_role():
    """OIDC mode should accept validated tokens whose claims resolve to an allowed role."""
    service = AuthenticationService(
        build_test_settings(
            auth_mode="oidc_jwt",
            authorization_enabled=True,
            user_groups=("Codex-Users",),
        )
    )

    with patch.object(
        AuthenticationService,
        "_decode_oidc_token",
        return_value={
            "sub": "charlie",
            "preferred_username": "charlie",
            "groups": ["Codex-Users"],
        },
    ):
        principal = service.resolve_principal(
            build_request(headers={"Authorization": "Bearer dummy-token"})
        )

    assert principal is not None
    assert principal.subject == "charlie"
    assert principal.roles == ("user",)
    assert service.require_execute_task_access(principal).subject == "charlie"


def test_require_admin_access_returns_local_principal_when_auth_is_disabled():
    service = AuthenticationService(build_test_settings(auth_mode="disabled"))

    principal = service.require_admin_access(None)

    assert principal.subject == "local-development"
    assert principal.roles == ("admin",)


def test_require_admin_access_requires_authentication_when_enabled():
    service = AuthenticationService(build_test_settings(auth_mode="trusted_header"))

    with pytest.raises(AuthenticationRequiredError):
        service.require_admin_access(None)


def test_require_admin_access_denies_non_admin_role():
    service = AuthenticationService(build_test_settings(auth_mode="trusted_header"))
    principal = service.resolve_principal(
        build_request(
            headers={
                "X-Authenticated-User": "alice",
                "X-Authenticated-Roles": "user",
            }
        )
    )

    with pytest.raises(AuthorizationDeniedError):
        service.require_admin_access(principal)
