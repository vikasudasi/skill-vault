from __future__ import annotations

from skill_vault.models import (
    DeleteResult,
    PublishResult,
    SkillCard,
    SkillDetail,
    SkillInput,
    VerifyResult,
)

SV_UNAUTHENTICATED = "SV_UNAUTHENTICATED"
SV_FORBIDDEN = "SV_FORBIDDEN"
SV_NOT_FOUND = "SV_NOT_FOUND"
SV_INVALID_SKILL = "SV_INVALID_SKILL"
SV_INTEGRITY = "SV_INTEGRITY"
SV_RATE_LIMITED = "SV_RATE_LIMITED"
SV_CONFLICT = "SV_CONFLICT"


class SkillVaultError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def search_skills(
    query: str,
    scope: str = "global",
    limit: int = 10,
    min_trust: str | None = None,
    agent_key: str | None = None,
) -> list[SkillCard]:
    """SkillCard = {id, name, description, tags, trust, score, version} - lightweight, no body.

    Scope semantics:
    - global -> any agent (even unauthenticated) may search the curated global store.
    - personal -> only that agent's private vault (requires valid agent_key).
    - all -> union of global + own personal (requires agent_key).

    Errors: SV_UNAUTHENTICATED, SV_FORBIDDEN, SV_RATE_LIMITED.
    """
    raise NotImplementedError(SV_UNAUTHENTICATED)


def get_skill(id: str, agent_key: str | None = None) -> SkillDetail:
    """SkillDetail = {
        id, name, description, body, version, tags, trust, content_hash, verified, owner
    }.

    Full body returned. Server re-derives sha256(body) and verifies it matches content_hash before
    returning. On mismatch, raises SV_INTEGRITY and never returns tampered content.

    Errors: SV_NOT_FOUND, SV_FORBIDDEN, SV_INTEGRITY.
    """
    raise NotImplementedError(SV_NOT_FOUND)


def publish_skill(
    skill: SkillInput,
    visibility: str = "personal",
    *,
    agent_key: str,
) -> PublishResult:
    """SkillInput = {name, description, tags[], triggers[], body, meta{}}.

    Creates a new skill; duplicate name in requesting agent scope returns SV_CONFLICT (use
    update_skill). Assigns version=1, content_hash=sha256(canonical(skill)), trust='user' (personal)
    or 'public' (global, if publishing allowed).

    Errors: SV_UNAUTHENTICATED, SV_INVALID_SKILL, SV_CONFLICT, SV_FORBIDDEN.
    """
    raise NotImplementedError(SV_INVALID_SKILL)


def update_skill(id: str, skill: SkillInput, agent_key: str) -> PublishResult:
    """Only the owning agent (or curator for global seed) may update.

    Appends a new immutable version (version=max+1), updates current_version_id.
    Previous versions remain addressable/hash-pinned.

    Errors: SV_UNAUTHENTICATED, SV_NOT_FOUND, SV_FORBIDDEN, SV_INVALID_SKILL.
    """
    raise NotImplementedError(SV_NOT_FOUND)


def list_my_skills(agent_key: str, scope: str = "all") -> list[SkillCard]:
    """List cards (no bodies) for the authenticated agent's personal vault and optional global scope.

    Errors: SV_UNAUTHENTICATED, SV_FORBIDDEN.
    """
    raise NotImplementedError(SV_UNAUTHENTICATED)


def delete_skill(id: str, agent_key: str) -> DeleteResult:
    """Owner-only soft delete (marks removed), while keeping version history for audit.

    Errors: SV_UNAUTHENTICATED, SV_NOT_FOUND, SV_FORBIDDEN.
    """
    raise NotImplementedError(SV_FORBIDDEN)


def verify_skill(id: str) -> VerifyResult:
    """Return {trust, verified: bool, signed_by, content_hash} for current version.

    Errors: SV_NOT_FOUND, SV_INTEGRITY.
    """
    raise NotImplementedError(SV_INTEGRITY)
