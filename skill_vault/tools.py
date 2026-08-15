"""MCP tool surface — thin FastMCP bindings over the :class:`RegistryService`.

The tools delegate to the registry service (``service.py``) and translate domain
errors (``SV_*`` codes) into MCP errors. Kept thin by design so all business
logic stays unit-testable without an MCP runtime.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastmcp import FastMCP

from skill_vault.db import locked
from skill_vault.errors import SkillVaultError
from skill_vault.models import (
    DeleteResult,
    PublishResult,
    SkillCard,
    SkillDetail,
    SkillFile,
    SkillFileDetail,
    SkillInput,
)
from skill_vault.service import RegistryService


def _header_agent_key() -> str | None:
    """Resolve the agent API key from the current HTTP request headers.

    Supported headers (case-insensitive):
    - ``Authorization: Bearer <key>`` (primary)
    - ``X-Agent-Key: <key>`` (alternative)

    Returns ``None`` when no request context is present or no usable header
    is found.
    """
    try:
        from fastmcp.server.dependencies import get_http_request

        req = get_http_request()
    except (ImportError, LookupError, RuntimeError):
        return None
    hdr: str | None = None
    auth = req.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        hdr = auth[7:].strip() or None
    if hdr is None:
        x = req.headers.get("x-agent-key")
        hdr = (x or "").strip() or None
    return hdr


def _resolve_agent_key(agent_key: str | None) -> str | None:
    """Return the effective agent key: explicit per-call arg wins, else header."""
    return agent_key if agent_key else _header_agent_key()


@contextmanager
def _translate_errors() -> Iterator[None]:
    try:
        yield
    except SkillVaultError as exc:
        raise ValueError(f"{exc.code}: {exc}") from exc


def register_tools(server: FastMCP, registry: RegistryService) -> None:
    """Register the Skill Vault tool surface on ``server`` against ``registry``."""

    @server.tool(
        description=(
            "Find skills relevant to a task by semantic similarity. Preferred over listing when you "
            "need the BEST match on a topic (e.g. 'how do I write a pytest fixture'). Returns lightweight "
            "cards with a relevance score. scope: 'global' (default, no key needed) | 'all' / 'personal' "
            "(requires agent_key). Optional min_trust filters results to a minimum trust tier."
        )
    )
    def search_skills(
        query: str,
        scope: str = "global",
        limit: int = 10,
        min_trust: str | None = None,
        agent_key: str | None = None,
    ) -> list[SkillCard]:
        with locked(), _translate_errors():
            return registry.search(
                query=query,
                scope=scope,
                limit=limit,
                min_trust=min_trust,
                agent_key=_resolve_agent_key(agent_key),
            )

    @server.tool(
        description=(
            "Fetch the FULL content of a skill (SKILL.md body + trust/verified/content_hash) by id or "
            "version id. Use when you need the actual skill text/instructions, not just a card. Global "
            "skills are readable by anyone; personal/team skills require the owning agent_key. Use "
            "search_skills first to find an id if you don't have one."
        )
    )
    def get_skill(id: str, version: int | None = None, agent_key: str | None = None) -> SkillDetail:
        with locked(), _translate_errors():
            return registry.get(
                identifier=id, version=version, agent_key=_resolve_agent_key(agent_key)
            )

    @server.tool(
        description=(
            "Create a NEW skill (version 1). visibility: 'personal' (default) | 'team' | 'global'. "
            "IMPORTANT: a normal agent key may only publish to 'personal'/'team' — publishing to 'global' "
            "requires a SUPER-AGENT key or admin and raises SV_FORBIDDEN otherwise. Raises SV_CONFLICT if a "
            "skill with that name already exists in your scope — in that case use update_skill instead."
        )
    )
    def publish_skill(
        skill: SkillInput, visibility: str = "personal", agent_key: str | None = None
    ) -> PublishResult:
        with locked(), _translate_errors():
            return registry.publish(
                skill=skill, visibility=visibility, agent_key=_resolve_agent_key(agent_key)
            )

    @server.tool(
        description=(
            "Append a new immutable VERSION to an existing skill you own (version = max+1, previous "
            "versions stay hash-pinned and addressable). Use instead of publish_skill when the skill name "
            "already exists in your scope. Only the owning agent may update; updating a 'global' skill "
            "requires a super-agent key or admin (else SV_FORBIDDEN). Global updates by a super-agent "
            "auto-sign to trust tier 'verified'."
        )
    )
    def update_skill(id: str, skill: SkillInput, agent_key: str | None = None) -> PublishResult:
        with locked(), _translate_errors():
            return registry.update(
                identifier=id, skill=skill, agent_key=_resolve_agent_key(agent_key)
            )

    @server.tool(
        description=(
            "Permanently delete a skill you own (owner-only; version history is kept for audit). Use only "
            "when the skill should no longer exist at all. For corrective content changes, prefer "
            "update_skill (creates a new version) so history is preserved."
        )
    )
    def delete_skill(id: str, agent_key: str | None = None) -> DeleteResult:
        with locked(), _translate_errors():
            return registry.delete(identifier=id, agent_key=_resolve_agent_key(agent_key))

    @server.tool(
        description=(
            "List cards (no bodies) for the authenticated agent's PERSONAL skills only. Use to enumerate "
            "your own vault (e.g. 'what did I publish?'). For the public store use list_global_skills; for "
            "topic discovery use search_skills. Requires agent_key."
        )
    )
    def list_my_skills(agent_key: str | None = None) -> list[SkillCard]:
        with locked(), _translate_errors():
            return registry.list_my(agent_key=_resolve_agent_key(agent_key))

    @server.tool(
        description=(
            "Browse the curated GLOBAL (public) skill store as paged cards (no bodies, no key needed). Use "
            "to enumerate/explore the public library; use search_skills when you want relevance-ranked "
            "matches on a topic instead of a flat page."
        )
    )
    def list_global_skills(limit: int = 20, offset: int = 0) -> list[SkillCard]:
        with locked(), _translate_errors():
            return registry.list_global(limit=limit, offset=offset)

    @server.tool(
        description=(
            "Attach a script or reference file to an existing skill version. kind must be "
            "'script' or 'reference'. filename must be unique within the version. Returns file "
            "metadata (no content in list views; use get_skill_file for full content)."
        )
    )
    def upload_skill_file(
        skill_version_id: str, kind: str, filename: str, content: str
    ) -> SkillFileDetail:
        with locked(), _translate_errors():
            sf = registry.add_skill_file(skill_version_id, kind, filename, content)
            return SkillFileDetail(
                id=sf.id,
                kind=sf.kind,
                filename=sf.filename,
                content_hash=sf.content_hash,
                created_at=sf.created_at,
            )

    @server.tool(
        description=(
            "List attached script/reference files for a skill version (metadata only, no content). "
            "Use get_skill_file to fetch full file content."
        )
    )
    def list_skill_files(skill_version_id: str) -> list[SkillFileDetail]:
        with locked(), _translate_errors():
            return registry.list_skill_files(skill_version_id)

    @server.tool(
        description=("Fetch the full content of an attached script or reference file by file id.")
    )
    def get_skill_file(file_id: str) -> SkillFile:
        with locked(), _translate_errors():
            return registry.get_skill_file(file_id)
