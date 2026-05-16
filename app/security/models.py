"""Security-related domain models for authenticated request context."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserPrincipal:
    """Represents the effective caller identity for a single API request.

    This object is created by the authentication service and attached to
    the request context.

    Attributes:
        subject: The unique identifier of the user (e.g., OIDC 'sub').
        username: The display username.
        auth_mode: The authentication method used ("trusted_header", "oidc_jwt", or "disabled").
        roles: Application-level roles assigned to the user.
        groups: External groups the user belongs to.
        email: Optional user email address.
        tenant_id: Optional tenant identifier.
    """

    subject: str
    username: str
    auth_mode: str
    roles: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()
    email: str | None = None
    tenant_id: str | None = None

    @property
    def display_name(self) -> str:
        """Returns the most useful human-facing identity string for logs.

        Returns:
            A string identifying the user (email, username, or subject).
        """
        return self.email or self.username or self.subject
