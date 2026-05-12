"""Security-related domain models for authenticated request context."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserPrincipal:
    """Represents the effective caller identity for a single API request."""

    subject: str
    username: str
    auth_mode: str
    roles: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()
    email: str | None = None
    tenant_id: str | None = None

    @property
    def display_name(self) -> str:
        """Return the most useful human-facing identity string for logs."""
        return self.email or self.username or self.subject
