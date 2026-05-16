"""Granular unit tests for the AuthenticationService logic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import AuthenticationFailedError, ConfigurationError
from app.security.authentication import AuthenticationService
from tests.support import build_test_settings


def _build_request(headers: dict[str, str], host: str = "127.0.0.1") -> MagicMock:
    """Helper to build a mock FastAPI request with headers and client info."""
    request = MagicMock()
    request.headers = headers
    request.client.host = host
    return request


def test_trusted_header_resolves_identity_and_roles():
    """Service should map headers to a principal with correct roles and groups."""
    settings = build_test_settings(
        auth_mode="trusted_header",
        authorization_enabled=True,
        admin_groups=["Admins"],
        user_groups=["Users"],
    )
    service = AuthenticationService(settings=settings)

    headers = {
        "X-Authenticated-User": "alice",
        "X-Authenticated-Groups": "Admins;Developers",
        "X-Authenticated-Roles": "custom-role",
    }
    request = _build_request(headers)

    principal = service.resolve_principal(request)

    assert principal is not None
    assert principal.subject == "alice"
    assert principal.username == "alice"
    assert "admin" in principal.roles
    assert "custom-role" in principal.roles
    assert "Admins" in principal.groups


def test_trusted_header_rejects_untrusted_proxy():
    """Service should raise an error if headers come from an unauthorized IP."""
    settings = build_test_settings(
        auth_mode="trusted_header",
        trusted_proxy_ips=["10.0.0.1"],
    )
    service = AuthenticationService(settings=settings)

    headers = {"X-Authenticated-User": "alice"}
    request = _build_request(headers, host="192.168.1.1")

    with pytest.raises(AuthenticationFailedError) as exc_info:
        service.resolve_principal(request)
    assert "untrusted source" in exc_info.value.message


def test_oidc_claim_normalization_handles_lists_and_strings():
    """Service should correctly handle both list and string claims from JWT."""
    service = AuthenticationService(settings=build_test_settings())

    # Internal method test via direct access (mocking JWT decoding results)
    claims = {
        "groups": ["group1", "group2"],
        "roles": "role1",
    }

    groups = service._claim_values(claims.get("groups"))
    roles = service._claim_values(claims.get("roles"))

    assert groups == ("group1", "group2")
    assert roles == ("role1",)


def test_auth_service_denies_access_without_required_role():
    """Service should raise AuthorizationDeniedError if user lacks allowed roles."""
    settings = build_test_settings(
        auth_mode="trusted_header",
        authorization_enabled=True,
        execute_task_roles=["admin"],
    )
    service = AuthenticationService(settings=settings)

    # Alice has only 'user' role
    headers = {
        "X-Authenticated-User": "alice",
        "X-Authenticated-Roles": "user",
    }
    request = _build_request(headers)
    principal = service.resolve_principal(request)

    from app.core.exceptions import AuthorizationDeniedError

    with pytest.raises(AuthorizationDeniedError):
        service.require_execute_task_access(principal)


def test_auth_service_allows_access_without_roles_configured():
    settings = build_test_settings(
        auth_mode="trusted_header",
        authorization_enabled=True,
        execute_task_roles=(),
    )
    service = AuthenticationService(settings=settings)
    headers = {"X-Authenticated-User": "alice"}
    request = _build_request(headers)
    principal = service.resolve_principal(request)
    assert service.require_execute_task_access(principal).subject == "alice"


def test_auth_service_unsupported_mode():
    settings = build_test_settings()
    object.__setattr__(settings.auth, "mode", "invalid_mode")
    service = AuthenticationService(settings=settings)
    request = _build_request({})
    with pytest.raises(ConfigurationError, match="Unsupported auth mode"):
        service.resolve_principal(request)


def test_readiness_components_disabled():
    settings = build_test_settings(auth_mode="disabled")
    service = AuthenticationService(settings=settings)
    components = service.readiness_components()
    assert len(components) == 1
    assert components[0].status == "up"
    assert "disabled" in components[0].details


def test_readiness_components_trusted_header():
    settings = build_test_settings(auth_mode="trusted_header")
    service = AuthenticationService(settings=settings)
    components = service.readiness_components()
    assert len(components) == 1
    assert components[0].status == "up"
    assert "Trusted-header authentication enabled" in components[0].details


def test_readiness_components_oidc_jwt_ready():
    settings = build_test_settings(auth_mode="oidc_jwt")
    object.__setattr__(settings.auth.oidc, "issuer", "issuer")
    object.__setattr__(settings.auth.oidc, "jwks_url", "jwks_url")
    service = AuthenticationService(settings=settings)
    with patch.object(service, "_oidc_dependency_status", return_value=[]):
        components = service.readiness_components()
        assert components[0].status == "up"


def test_readiness_components_oidc_jwt_missing():
    settings = build_test_settings(auth_mode="oidc_jwt")
    object.__setattr__(settings.auth.oidc, "issuer", "")
    object.__setattr__(settings.auth.oidc, "jwks_url", "")
    service = AuthenticationService(settings=settings)
    components = service.readiness_components()
    assert components[0].status == "down"
    assert "issuer is missing" in components[0].details
    assert "jwks_url is missing" in components[0].details


def test_authenticate_via_oidc_jwt_missing_token():
    settings = build_test_settings(auth_mode="oidc_jwt")
    service = AuthenticationService(settings=settings)
    request = _build_request({})
    assert service._authenticate_via_oidc_jwt(request) is None


def test_authenticate_via_oidc_jwt_missing_subject():
    settings = build_test_settings(auth_mode="oidc_jwt")
    service = AuthenticationService(settings=settings)
    request = _build_request({"Authorization": "Bearer token123"})

    with patch.object(service, "_decode_oidc_token", return_value={"sub": ""}):
        with pytest.raises(
            AuthenticationFailedError,
            match="does not contain the configured subject claim",
        ):
            service._authenticate_via_oidc_jwt(request)


def test_decode_oidc_token_missing_settings():
    settings = build_test_settings(auth_mode="oidc_jwt")
    object.__setattr__(settings.auth.oidc, "issuer", "")
    service = AuthenticationService(settings=settings)

    with patch.object(service, "_oidc_dependency_status", return_value=[]):
        with pytest.raises(ConfigurationError, match="misconfigured"):
            service._decode_oidc_token("token123")


def test_decode_oidc_token_no_audience_and_configuration_error():
    settings = build_test_settings(auth_mode="oidc_jwt", oidc_audience=None)
    service = AuthenticationService(settings=settings)

    with (
        patch.object(service, "_oidc_dependency_status", return_value=[]),
        patch("app.security.authentication._build_jwk_client") as mock_jwk,
        patch("app.security.authentication.importlib.import_module") as mock_import,
    ):
        # Test 1: ConfigurationError passthrough
        mock_jwk.return_value.get_signing_key_from_jwt.side_effect = ConfigurationError(
            "test"
        )
        with pytest.raises(ConfigurationError, match="test"):
            service._decode_oidc_token("token123")

        # Test 2: no audience sets verify_aud=False
        mock_key = MagicMock()
        mock_key.key = "key"
        mock_jwk.return_value.get_signing_key_from_jwt.side_effect = None
        mock_jwk.return_value.get_signing_key_from_jwt.return_value = mock_key

        mock_jwt = MagicMock()
        mock_import.return_value = mock_jwt
        service._decode_oidc_token("token123")
        mock_jwt.decode.assert_called_once()
        args, kwargs = mock_jwt.decode.call_args
        assert kwargs["options"]["verify_aud"] is False


def test_extract_bearer_token_empty():
    settings = build_test_settings()
    service = AuthenticationService(settings=settings)
    assert service._extract_bearer_token(None) is None
    with pytest.raises(AuthenticationFailedError, match="use the Bearer scheme"):
        service._extract_bearer_token("Basic 123")
    with pytest.raises(
        AuthenticationFailedError, match="does not contain a bearer token"
    ):
        service._extract_bearer_token("Bearer   ")


def test_require_oidc_dependencies():
    settings = build_test_settings(auth_mode="oidc_jwt")
    service = AuthenticationService(settings=settings)
    with patch.object(service, "_oidc_dependency_status", return_value=["missing"]):
        with pytest.raises(ConfigurationError, match="dependencies are not installed"):
            service._require_oidc_dependencies()


def test_claim_values_list_with_none():
    settings = build_test_settings()
    service = AuthenticationService(settings=settings)
    assert service._claim_values(None) == ()
    assert service._claim_values(["a", None, "b", " "]) == ("a", "None", "b")
