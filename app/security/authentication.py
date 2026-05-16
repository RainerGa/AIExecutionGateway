"""Authentication and authorization services with profile-driven runtime modes."""

from __future__ import annotations

import importlib
import importlib.util
import logging
from functools import lru_cache
from typing import Any

from fastapi import Request

from app.core.config import AppSettings
from app.core.exceptions import (
    AuthenticationFailedError,
    AuthenticationRequiredError,
    AuthorizationDeniedError,
    ConfigurationError,
)
from app.schemas.health import HealthComponent
from app.security.models import UserPrincipal

LOGGER = logging.getLogger(__name__)
_BEARER_PREFIX = "bearer "


@lru_cache(maxsize=8)
def _build_jwk_client(jwks_url: str):
    """Cache JWT key clients per JWKS URL to avoid repeated bootstrap work."""
    jwt_module = importlib.import_module("jwt")
    return jwt_module.PyJWKClient(jwks_url)


class AuthenticationService:
    """Resolve the current caller identity and enforce access control."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def resolve_principal(self, request: Request) -> UserPrincipal | None:
        """Resolve the caller identity for the current request and auth mode."""
        auth_mode = self.settings.auth.mode

        if auth_mode == "disabled":
            return self._build_disabled_principal()
        if auth_mode == "trusted_header":
            return self._authenticate_via_trusted_headers(request)
        if auth_mode == "oidc_jwt":
            return self._authenticate_via_oidc_jwt(request)

        raise ConfigurationError(f"Unsupported auth mode configured: {auth_mode}")

    def require_execute_task_access(
        self,
        principal: UserPrincipal | None,
    ) -> UserPrincipal:
        """Enforce authentication and authorization for task execution endpoints."""
        if self.settings.auth.mode == "disabled":
            return principal or self._build_disabled_principal()

        if principal is None:
            raise AuthenticationRequiredError(
                "Authentication is required to execute tasks.",
                headers=self._auth_headers(),
            )

        if not self.settings.auth.authorization.enabled:
            return principal

        allowed_roles = set(self.settings.auth.authorization.execute_task_roles)
        effective_roles = set(principal.roles)
        if allowed_roles and not effective_roles.intersection(allowed_roles):
            raise AuthorizationDeniedError(
                "The authenticated user is not allowed to execute tasks.",
            )

        return principal

    def require_admin_access(
        self,
        principal: UserPrincipal | None,
    ) -> UserPrincipal:
        """Require an authenticated principal with the admin role."""
        if self.settings.auth.mode == "disabled":
            return principal or self._build_disabled_principal()

        if principal is None:
            raise AuthenticationRequiredError(
                "Authentication is required to access monitoring endpoints.",
                headers=self._auth_headers(),
            )

        if "admin" not in set(principal.roles):
            raise AuthorizationDeniedError(
                "The authenticated user is not allowed to access monitoring endpoints.",
            )

        return principal

    def readiness_components(self) -> list[HealthComponent]:
        """Return health components describing the configured auth subsystem."""
        if self.settings.auth.mode == "disabled":
            return [
                HealthComponent(
                    name="authentication",
                    status="up",
                    details="Authentication is disabled for the active profile.",
                )
            ]

        if self.settings.auth.mode == "trusted_header":
            trusted_proxy_text = (
                ", ".join(self.settings.auth.trusted_header.trusted_proxy_ips)
                if self.settings.auth.trusted_header.trusted_proxy_ips
                else "all sources"
            )
            return [
                HealthComponent(
                    name="authentication",
                    status="up",
                    details=(
                        "Trusted-header authentication enabled via "
                        f"{self.settings.auth.trusted_header.user_header}; "
                        f"trusted proxies: {trusted_proxy_text}."
                    ),
                )
            ]

        missing_dependencies = self._oidc_dependency_status()
        missing_settings = self._oidc_missing_settings()
        if missing_dependencies or missing_settings:
            problems = missing_dependencies + missing_settings
            return [
                HealthComponent(
                    name="authentication",
                    status="down",
                    details="OIDC authentication is not ready: " + "; ".join(problems),
                )
            ]

        return [
            HealthComponent(
                name="authentication",
                status="up",
                details="OIDC JWT authentication is configured.",
            )
        ]

    def _build_disabled_principal(self) -> UserPrincipal:
        """Provide a deterministic local-development principal when auth is disabled."""
        return UserPrincipal(
            subject="local-development",
            username="local-development",
            auth_mode="disabled",
            roles=("admin",),
        )

    def _authenticate_via_trusted_headers(
        self, request: Request
    ) -> UserPrincipal | None:
        """Resolve identity information from trusted reverse-proxy headers."""
        header_settings = self.settings.auth.trusted_header
        subject = (request.headers.get(header_settings.user_header) or "").strip()
        if not subject:
            return None

        if not self._request_origin_is_trusted(request):
            raise AuthenticationFailedError(
                "Trusted authentication headers were received from an untrusted source.",
            )

        groups = self._split_values(
            request.headers.get(header_settings.groups_header),
            separator=header_settings.group_separator,
        )
        explicit_roles = self._split_values(
            request.headers.get(header_settings.roles_header),
            separator=header_settings.group_separator,
        )
        roles = self._combine_roles(explicit_roles, self._map_group_roles(groups))

        return UserPrincipal(
            subject=subject,
            username=subject,
            auth_mode="trusted_header",
            roles=roles,
            groups=groups,
            email=(request.headers.get(header_settings.email_header) or "").strip()
            or None,
        )

    def _authenticate_via_oidc_jwt(self, request: Request) -> UserPrincipal | None:
        """Resolve identity from an incoming bearer token using OIDC metadata."""
        token = self._extract_bearer_token(request.headers.get("Authorization"))
        if token is None:
            return None

        claims = self._decode_oidc_token(token)
        oidc_settings = self.settings.auth.oidc

        subject = str(claims.get(oidc_settings.subject_claim) or "").strip()
        if not subject:
            raise AuthenticationFailedError(
                "Validated token does not contain the configured subject claim.",
                headers=self._auth_headers(),
            )

        groups = self._claim_values(claims.get(oidc_settings.groups_claim))
        explicit_roles = self._claim_values(claims.get(oidc_settings.roles_claim))
        roles = self._combine_roles(explicit_roles, self._map_group_roles(groups))

        return UserPrincipal(
            subject=subject,
            username=str(claims.get(oidc_settings.username_claim) or subject).strip()
            or subject,
            auth_mode="oidc_jwt",
            roles=roles,
            groups=groups,
            email=(
                str(claims.get(oidc_settings.email_claim)).strip()
                if claims.get(oidc_settings.email_claim)
                else None
            ),
            tenant_id=(
                str(claims.get(oidc_settings.tenant_claim)).strip()
                if claims.get(oidc_settings.tenant_claim)
                else None
            ),
        )

    def _decode_oidc_token(self, token: str) -> dict[str, Any]:
        """Validate and decode a bearer token using the configured OIDC metadata."""
        self._require_oidc_dependencies()
        missing_settings = self._oidc_missing_settings()
        if missing_settings:
            raise ConfigurationError(
                "OIDC authentication is misconfigured.",
                details="; ".join(missing_settings),
            )

        oidc_settings = self.settings.auth.oidc
        jwt_module = importlib.import_module("jwt")
        jwk_client = _build_jwk_client(oidc_settings.jwks_url or "")

        try:
            signing_key = jwk_client.get_signing_key_from_jwt(token)
            options: dict[str, Any] = {"require": list(oidc_settings.required_claims)}
            if not oidc_settings.audience:
                options["verify_aud"] = False

            return jwt_module.decode(
                token,
                signing_key.key,
                algorithms=list(oidc_settings.algorithms),
                audience=oidc_settings.audience,
                issuer=oidc_settings.issuer,
                options=options,
                leeway=oidc_settings.clock_skew_seconds,
            )
        except ConfigurationError:
            raise
        except Exception as exc:
            raise AuthenticationFailedError(
                "OIDC token validation failed.",
                details=str(exc),
                headers=self._auth_headers(),
            ) from exc

    def _request_origin_is_trusted(self, request: Request) -> bool:
        """Check whether trusted-auth headers are allowed from the request source."""
        trusted_proxy_ips = self.settings.auth.trusted_header.trusted_proxy_ips
        if not trusted_proxy_ips:
            return True

        client = request.client
        return bool(client and client.host in trusted_proxy_ips)

    def _map_group_roles(self, groups: tuple[str, ...]) -> tuple[str, ...]:
        """Translate directory groups into application roles using config mappings."""
        authorization_settings = self.settings.auth.authorization
        roles: set[str] = set()
        group_set = set(groups)

        if group_set.intersection(authorization_settings.admin_groups):
            roles.add("admin")
        if group_set.intersection(authorization_settings.user_groups):
            roles.add("user")
        if group_set.intersection(authorization_settings.readonly_groups):
            roles.add("readonly")

        return tuple(sorted(roles))

    def _combine_roles(
        self,
        explicit_roles: tuple[str, ...],
        mapped_roles: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Merge explicit role claims with group-derived roles."""
        return tuple(sorted({*explicit_roles, *mapped_roles}))

    def _extract_bearer_token(self, authorization_header: str | None) -> str | None:
        """Extract a bearer token from the Authorization header when present."""
        if not authorization_header:
            return None

        value = authorization_header.lstrip()
        if value[:7].lower() != _BEARER_PREFIX:
            raise AuthenticationFailedError(
                "Authorization header must use the Bearer scheme.",
                headers=self._auth_headers(),
            )

        token = value[7:].strip()
        if not token:
            raise AuthenticationFailedError(
                "Authorization header does not contain a bearer token.",
                headers=self._auth_headers(),
            )
        return token

    def _split_values(
        self, raw_value: str | None, *, separator: str
    ) -> tuple[str, ...]:
        """Split delimited header values into a normalized tuple."""
        if not raw_value:
            return ()

        values = [value.strip() for value in raw_value.split(separator)]
        return tuple(value for value in values if value)

    def _claim_values(self, raw_value: Any) -> tuple[str, ...]:
        """Normalize scalar or list-style JWT claim values into strings."""
        if raw_value is None:
            return ()
        if isinstance(raw_value, str):
            value = raw_value.strip()
            return (value,) if value else ()
        if isinstance(raw_value, (list, tuple)):
            values = []
            for item in raw_value:
                value = str(item).strip()
                if value:
                    values.append(value)
            return tuple(values)
        return (str(raw_value).strip(),) if str(raw_value).strip() else ()

    def _oidc_dependency_status(self) -> list[str]:
        """Report missing Python modules needed for JWT validation."""
        missing_dependencies = []
        if importlib.util.find_spec("jwt") is None:
            missing_dependencies.append("PyJWT is not installed")
        if importlib.util.find_spec("cryptography") is None:
            missing_dependencies.append("cryptography is not installed")
        return missing_dependencies

    def _oidc_missing_settings(self) -> list[str]:
        """Report incomplete OIDC configuration for readiness and startup checks."""
        oidc_settings = self.settings.auth.oidc
        missing = []
        if not oidc_settings.issuer:
            missing.append("issuer is missing")
        if not oidc_settings.jwks_url:
            missing.append("jwks_url is missing")
        return missing

    def _require_oidc_dependencies(self) -> None:
        """Raise a configuration error if the JWT validation stack is unavailable."""
        missing_dependencies = self._oidc_dependency_status()
        if missing_dependencies:
            raise ConfigurationError(
                "OIDC authentication dependencies are not installed.",
                details="; ".join(missing_dependencies),
            )

    def _auth_headers(self) -> dict[str, str]:
        """Build protocol-appropriate headers for authentication failures."""
        if self.settings.auth.mode == "oidc_jwt":
            return {"WWW-Authenticate": "Bearer"}
        return {}
