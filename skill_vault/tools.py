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
from skill_vault.models import DeleteResult, PublishResult, SkillCard, SkillDetail, SkillInput
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

    @server.tool(description="Semantic search for relevant skills by natural-language query.")
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

    @server.tool(description="Fetch the full content of a skill by id or version id.")
    def get_skill(id: str, version: int | None = None, agent_key: str | None = None) -> SkillDetail:
        with locked(), _translate_errors():
            return registry.get(
                identifier=id, version=version, agent_key=_resolve_agent_key(agent_key)
            )

    @server.tool(description="Publish a new skill to your vault (global, team, or personal).")
    def publish_skill(
        skill: SkillInput, visibility: str = "personal", agent_key: str | None = None
    ) -> PublishResult:
        with locked(), _translate_errors():
            return registry.publish(
                skill=skill, visibility=visibility, agent_key=_resolve_agent_key(agent_key)
            )

    @server.tool(description="Update an existing skill you own (creates a new version).")
    def update_skill(id: str, skill: SkillInput, agent_key: str | None = None) -> PublishResult:
        with locked(), _translate_errors():
            return registry.update(
                identifier=id, skill=skill, agent_key=_resolve_agent_key(agent_key)
            )

    @server.tool(description="Delete a skill you own.")
    def delete_skill(id: str, agent_key: str | None = None) -> DeleteResult:
        with locked(), _translate_errors():
            return registry.delete(identifier=id, agent_key=_resolve_agent_key(agent_key))

    @server.tool(description="List the skills in your personal vault.")
    def list_my_skills(agent_key: str | None = None) -> list[SkillCard]:
        with locked(), _translate_errors():
            return registry.list_my(agent_key=_resolve_agent_key(agent_key))

    @server.tool(description="Browse the global (public) skill store with pagination.")
    def list_global_skills(limit: int = 20, offset: int = 0) -> list[SkillCard]:
        with locked(), _translate_errors():
            return registry.list_global(limit=limit, offset=offset)
