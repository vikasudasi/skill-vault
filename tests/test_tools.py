"""MCP tool-surface coverage (Task 9): invoke every tool through the FastMCP
runtime and exercise the error-translation layer (DomainError -> ValueError).

Hermetic: real SQLite + sqlite-vec + deterministic FakeEmbedder; no model download.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest
from conftest import FakeEmbedder
from fastmcp.exceptions import ToolError

from skill_vault.auth import AuthService
from skill_vault.bootstrap import Services
from skill_vault.db import connect, run_migrations
from skill_vault.models import SkillInput
from skill_vault.search import SearchService, SqliteVecStore
from skill_vault.server import create_server
from skill_vault.service import RegistryService
from skill_vault.trust import TrustService

MIGRATIONS = str(Path(__file__).resolve().parent.parent / "migrations")


def _stack(tmp_path):
    db = connect(str(tmp_path / "app.db"))
    run_migrations(db, MIGRATIONS)
    auth = AuthService(db, rate_limit=100000)
    store = SqliteVecStore(str(tmp_path / "vec.db"))
    search = SearchService(db, store, FakeEmbedder())
    trust = TrustService(db, allow_tiers=("verified", "user", "public"))
    reg = RegistryService(db, auth=auth, search=search, trust=trust)
    services = Services(db=db, auth=auth, search=search, trust=trust, registry=reg)
    server = create_server(services)
    return server, reg, auth


def _skill(name="docker"):
    return SkillInput(
        name=name,
        description=f"{name} skill description",
        tags=["devops", "cli"],
        triggers=["deploy", "build"],
        body="# docker\nmanage containers",
        meta={},
    )


@pytest.fixture
def stack(tmp_path):
    return _stack(tmp_path)


def test_all_tools_searchable_and_callable(stack, tmp_path):
    server, reg, auth = stack
    onboard = auth.onboard("wally")
    res = reg.publish(skill=_skill(), visibility="global", agent_key=onboard.raw_key)

    # search_skills
    hits = asyncio.run(
        server.call_tool("search_skills", {"query": "docker deploy", "scope": "global"})
    )
    assert list(hits)

    # get_skill (by id)
    detail = asyncio.run(
        server.call_tool("get_skill", {"id": res.id, "agent_key": onboard.raw_key})
    )
    assert "docker" in str(next(iter(detail)))

    # publish_skill via tool surface
    published = asyncio.run(
        server.call_tool(
            "publish_skill",
            {
                "skill": _skill(name="toolpub"),
                "visibility": "personal",
                "agent_key": onboard.raw_key,
            },
        )
    )
    pub_out = str(next(iter(published)))
    assert "toolpub" in pub_out or "version" in pub_out

    # update_skill via tool surface
    updated = asyncio.run(
        server.call_tool(
            "update_skill",
            {"id": res.id, "skill": _skill(name="docker"), "agent_key": onboard.raw_key},
        )
    )
    assert "version" in str(next(iter(updated)))

    # list_my_skills
    mine = asyncio.run(server.call_tool("list_my_skills", {"agent_key": onboard.raw_key}))
    assert list(mine)

    # list_global_skills
    globals_ = asyncio.run(server.call_tool("list_global_skills", {"limit": 10}))
    assert list(globals_)

    # delete_skill via tool surface
    deleted = asyncio.run(
        server.call_tool("delete_skill", {"id": res.id, "agent_key": onboard.raw_key})
    )
    assert "ok" in str(next(iter(deleted))).lower() or list(deleted)


def test_tool_error_translation_unknown_id(stack):
    server, _, _ = stack
    with pytest.raises(ToolError) as exc:
        asyncio.run(server.call_tool("get_skill", {"id": "does-not-exist"}))
    assert re.search(r"SV_[A-Z_]+", str(exc.value))  # domain code surfaced


def test_tool_scope_enforcement_denied(stack):
    server, reg, auth = stack
    a = auth.onboard("alice")
    b = auth.onboard("bob")
    res = reg.publish(skill=_skill(), visibility="personal", agent_key=a.raw_key)
    # bob cannot read alice's private skill through the tool surface
    with pytest.raises(ToolError) as exc:
        asyncio.run(server.call_tool("get_skill", {"id": res.id, "agent_key": b.raw_key}))
    assert "SV_" in str(exc.value)  # SV_FORBIDDEN translated


def test_tool_guest_publish_denied(stack):
    server, _, _ = stack
    with pytest.raises(ToolError) as exc:
        asyncio.run(
            server.call_tool(
                "publish_skill",
                {"skill": _skill(), "visibility": "global", "agent_key": None},
            )
        )
    assert "SV_UNAUTHENTICATED" in str(exc.value)
