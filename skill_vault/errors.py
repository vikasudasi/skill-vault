"""Skill Vault domain exceptions with stable public error codes.

Codes follow the SPEC SV_* convention. ``http_status`` maps to the REST/dashboard
layer; the MCP layer maps these to typed MCP errors with the same ``code`` string.
"""

from __future__ import annotations

from typing import ClassVar


class SkillVaultError(Exception):
    """Base error. ``code`` is the machine-readable SV_* identifier."""

    code: ClassVar[str] = "SV_ERROR"
    http_status: ClassVar[int] = 400

    def __init__(self, message: str = "") -> None:
        self.message = message or self.code
        super().__init__(self.message)


class AuthenticationError(SkillVaultError):
    code = "SV_UNAUTHENTICATED"
    http_status = 401


class RevokedKeyError(AuthenticationError):
    """A previously-issued key was presented after revocation."""

    code = "SV_KEY_REVOKED"


class ForbiddenError(SkillVaultError):
    code = "SV_FORBIDDEN"
    http_status = 403


class NotFoundError(SkillVaultError):
    code = "SV_NOT_FOUND"
    http_status = 404


class InvalidSkillError(SkillVaultError):
    code = "SV_INVALID_SKILL"
    http_status = 422


class RateLimitError(SkillVaultError):
    code = "SV_RATE_LIMITED"
    http_status = 429


class IntegrityError(SkillVaultError):
    code = "SV_INTEGRITY"
    http_status = 409
