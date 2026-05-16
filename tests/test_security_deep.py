"""Adversarial security tests for robust authentication and authorization.

These tests simulate malicious or malformed inputs to ensure the
security layer fails closed and remains stable.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request

from app.security.authentication import AuthenticationService
from app.core.exceptions import AuthenticationFailedError
from tests.support import build_test_settings


def _build_request(headers: dict[str, str], host: str = "127.0.0.1") -> MagicMock:
    request = MagicMock(spec=Request)
    request.headers = headers
    request.client.host = host
    return request


def test_trusted_header_injection_with_untrusted_proxy():
    """
    ADVERSARIAL TEST: Verifies that if a malicious client sends
    trusted-auth headers from an unauthorized IP, they are rejected.
    """
    # Only 10.0.0.1 is trusted
    settings = build_test_settings(
        auth_mode="trusted_header", trusted_proxy_ips=["10.0.0.1"]
    )
    service = AuthenticationService(settings=settings)

    # Attacker sends headers from a different IP
    headers = {"X-Authenticated-User": "admin"}
    request = _build_request(headers, host="192.168.5.55")

    with pytest.raises(AuthenticationFailedError) as exc_info:
        service.resolve_principal(request)
    assert "untrusted source" in str(exc_info.value).lower()


def test_bearer_token_malformed_schemes():
    """
    ADVERSARIAL TEST: Verifies that only the 'Bearer ' scheme is accepted.
    """
    settings = build_test_settings(auth_mode="oidc_jwt")
    service = AuthenticationService(settings=settings)

    # CASE 1: Basic Auth instead of Bearer
    req_basic = _build_request({"Authorization": "Basic YWxhZGRpbjpvcGVuc2VzYW1l"})
    with pytest.raises(AuthenticationFailedError) as exc:
        service.resolve_principal(req_basic)
    assert "bearer scheme" in str(exc.value).lower()

    # CASE 2: Empty Bearer
    req_empty = _build_request({"Authorization": "Bearer "})
    with pytest.raises(AuthenticationFailedError) as exc:
        service.resolve_principal(req_empty)
    assert "does not contain a bearer token" in str(exc.value).lower()


@patch("app.security.authentication.importlib.import_module")
@patch.object(AuthenticationService, "_require_oidc_dependencies", return_value=None)
def test_oidc_token_expired_signature(mock_require, mock_import):
    """
    ADVERSARIAL TEST: Verifies that expired tokens are correctly
    rejected by the OIDC validation logic.
    """
    settings = build_test_settings(auth_mode="oidc_jwt")
    service = AuthenticationService(settings=settings)

    mock_jwt = MagicMock()
    mock_import.return_value = mock_jwt

    # Use a dummy exception class for the mock side effect
    class ExpiredSignatureError(Exception):
        pass

    mock_jwt.decode.side_effect = ExpiredSignatureError("Signature has expired")

    # Mock JWK client to bypass network
    with patch("app.security.authentication._build_jwk_client") as mock_jwk:
        mock_jwk.return_value.get_signing_key_from_jwt.return_value = MagicMock()

        request = _build_request({"Authorization": "Bearer expired.token.here"})

        with pytest.raises(AuthenticationFailedError) as exc_info:
            service.resolve_principal(request)

        assert "validation failed" in str(exc_info.value).lower()
        assert "expired" in str(exc_info.value.details).lower()


def test_claim_normalization_vulnerabilities():
    """
    ADVERSARIAL TEST: Verifies that malformed or malicious claims
    (e.g., trying to inject objects into role lists) are normalized to strings.
    """
    service = AuthenticationService(settings=build_test_settings())

    # Malicious claim containing a dict instead of a string/list
    malicious_claims = {"roles": {"admin": True}}

    roles = service._claim_values(malicious_claims.get("roles"))

    # Should be normalized to its string representation, not executed or trusted as a list
    assert isinstance(roles, tuple)
    assert len(roles) == 1
    assert "admin" in str(roles[0])
