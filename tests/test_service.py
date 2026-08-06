"""End-to-end tests for the registry service + MCP tool surface (Task 2).

Uses a real SQLite DB + real sqlite-vec store + a deterministic fake embedder, so
the full storage/auth/search/trust stack is exercised without the huggingface model.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest
from conftest import FakeEmbedder

from skill_vault.auth import AuthService
from skill_vault.bootstrap import Services
from skill_vault.db import connect, run_migrations
from skill_vault.errors import AuthenticationError, ForbiddenError, InvalidSkillError, NotFoundError
from skill_vault.models import SkillInput
from skill_vault.search import SearchService, SqliteVecStore
from skill_vault.server import create_server
from skill_vault.service import RegistryService
from skill_vault.trust import TrustService

MIGRATIONS = str(Path(__file__).resolve().parent.parent / "migrations")


def _services(tmp_path):
    db = connect(str(tmp_path / "app.db"))
    run_migrations(db, MIGRATIONS)
    auth = AuthService(db, rate_limit=100000)
    store = SqliteVecStore(str(tmp_path / "vec.db"))
    search = SearchService(db, store, FakeEmbedder())
    trust = TrustService(db, allow_tiers=("verified", "user", "public"))
    reg = RegistryService(db, auth=auth, search=search, trust=trust)
    services = Services(db=db, auth=auth, search=search, trust=trust, registry=reg)
    return services, auth, reg


def _merged(tmp_path, name="docker"):
    services, auth, reg = _services(tmp_path)
    return services.db, auth, reg, auth.onboard(name)


def _skill(name="docker", body="# docker\nmanage containers"):
    return SkillInput(
        name=name,
        description=f"{name} skill description",
        tags=["devops", "cli"],
        triggers=["deploy", "build"],
        body=body,
        meta={},
    )


# --------------------------------------------------------------------------- #


def test_publish_then_get_roundtrip(tmp_path):
    _, _, reg, onboard = _merged(tmp_path)
    res = reg.publish(skill=_skill(), visibility="personal", agent_key=onboard.raw_key)
    assert res.ok and res.version == 1
    assert re.fullmatch(r"[0-9a-f]{64}", res.content_hash)

    detail = reg.get(identifier=res.id, agent_key=onboard.raw_key)
    assert detail.body == "# docker\nmanage containers"
    assert detail.version == 1
    assert detail.trust == "user"  # owned personal skill -> user tier
    assert detail.verified is False


def test_scope_isolation_personal(tmp_path):
    _, _, reg, a = _merged(tmp_path)
    b = reg._auth.onboard("agent-b")
    res = reg.publish(skill=_skill(), visibility="personal", agent_key=a.raw_key)

    assert reg.get(identifier=res.id, agent_key=a.raw_key).id == res.id  # owner ok
    with pytest.raises(ForbiddenError):  # other agent denied
        reg.get(identifier=res.id, agent_key=b.raw_key)
    with pytest.raises(AuthenticationError):  # guest denied
        reg.get(identifier=res.id, agent_key=None)


def test_global_visible_to_guest(tmp_path):
    _, _, reg, a = _merged(tmp_path)
    res = reg.publish(skill=_skill(), visibility="global", agent_key=a.raw_key)
    assert reg.get(identifier=res.id, agent_key=None).trust == "public"
    hits = reg.search(query="docker deploy", scope="global", agent_key=None)
    assert any(c.id == res.id for c in hits)


def test_team_publish_requires_user_owned_agent(tmp_path):
    _, _, reg, a = _merged(tmp_path)
    with pytest.raises(InvalidSkillError):
        reg.publish(skill=_skill(), visibility="team", agent_key=a.raw_key)


def test_team_scope_visibility_same_user_only(tmp_path):
    _, auth, reg = _services(tmp_path)
    user_a = auth.create_user("team-a@example.com", "password123")
    user_b = auth.create_user("team-b@example.com", "password123")
    agent_a = auth.onboard("team-owner", owner_user_id=user_a)
    agent_same_user = auth.onboard("team-peer", owner_user_id=user_a)
    agent_other_user = auth.onboard("team-other", owner_user_id=user_b)

    shared = reg.publish(skill=_skill(), visibility="team", agent_key=agent_a.raw_key)
    reg.publish(skill=_skill(name="global-shared"), visibility="global", agent_key=agent_a.raw_key)

    same_user_hits = reg.search(
        query="docker deploy", scope="team", agent_key=agent_same_user.raw_key
    )
    assert any(card.id == shared.id for card in same_user_hits)

    other_user_hits = reg.search(
        query="docker deploy", scope="team", agent_key=agent_other_user.raw_key
    )
    assert all(card.id != shared.id for card in other_user_hits)


def test_team_get_requires_same_user_agent(tmp_path):
    _, auth, reg = _services(tmp_path)
    user_a = auth.create_user("get-team-a@example.com", "password123")
    user_b = auth.create_user("get-team-b@example.com", "password123")
    owner = auth.onboard("team-owner", owner_user_id=user_a)
    same_user = auth.onboard("team-peer", owner_user_id=user_a)
    other_user = auth.onboard("team-outsider", owner_user_id=user_b)

    shared = reg.publish(skill=_skill(), visibility="team", agent_key=owner.raw_key)
    assert reg.get(identifier=shared.id, agent_key=same_user.raw_key).id == shared.id
    with pytest.raises(ForbiddenError):
        reg.get(identifier=shared.id, agent_key=other_user.raw_key)
    with pytest.raises(AuthenticationError):
        reg.get(identifier=shared.id, agent_key=None)


def test_team_and_all_scope_require_auth(tmp_path):
    _, _, reg, a = _merged(tmp_path)
    reg.publish(skill=_skill(), visibility="global", agent_key=a.raw_key)
    with pytest.raises(AuthenticationError):
        reg.search(query="docker", scope="team", agent_key=None)
    with pytest.raises(AuthenticationError):
        reg.search(query="docker", scope="all", agent_key=None)


def test_publish_requires_auth(tmp_path):
    _, _, reg = _services(tmp_path)
    with pytest.raises(AuthenticationError):
        reg.publish(skill=_skill(), visibility="global", agent_key=None)


def test_update_creates_new_version(tmp_path):
    _, _, reg, a = _merged(tmp_path)
    res = reg.publish(skill=_skill(), visibility="personal", agent_key=a.raw_key)
    v2 = reg.update(
        identifier=res.id, skill=_skill(body="# docker\nnew body v2"), agent_key=a.raw_key
    )
    assert v2.version == 2
    assert v2.content_hash != res.content_hash

    detail = reg.get(identifier=res.id, agent_key=a.raw_key)
    assert detail.version == 2 and detail.body == "# docker\nnew body v2"
    # old version retired from the semantic index -> exactly one card returned
    assert len(reg.search(query="docker deploy", scope="personal", agent_key=a.raw_key)) == 1


def test_delete_removes_skill(tmp_path):
    _, _, reg, a = _merged(tmp_path)
    res = reg.publish(skill=_skill(), visibility="personal", agent_key=a.raw_key)
    d = reg.delete(identifier=res.id, agent_key=a.raw_key)
    assert d.ok
    with pytest.raises(NotFoundError):
        reg.get(identifier=res.id, agent_key=a.raw_key)
    assert reg.list_my(agent_key=a.raw_key) == []


def test_cannot_update_or_delete_others_personal(tmp_path):
    _, _, reg, a = _merged(tmp_path)
    b = reg._auth.onboard("agent-b")
    res = reg.publish(skill=_skill(), visibility="personal", agent_key=a.raw_key)
    with pytest.raises(ForbiddenError):
        reg.update(identifier=res.id, skill=_skill(), agent_key=b.raw_key)
    with pytest.raises(ForbiddenError):
        reg.delete(identifier=res.id, agent_key=b.raw_key)


def test_list_my_and_list_global(tmp_path):
    _, _, reg, a = _merged(tmp_path)
    reg.publish(skill=_skill(name="one"), visibility="personal", agent_key=a.raw_key)
    reg.publish(skill=_skill(name="two"), visibility="global", agent_key=a.raw_key)
    mine = reg.list_my(agent_key=a.raw_key)
    assert {c.name for c in mine} == {"one", "two"}  # own personal + own global
    globals_ = reg.list_global()
    assert {c.name for c in globals_} == {"two"}
    with pytest.raises(AuthenticationError):  # guest cannot list own vault
        reg.list_my(agent_key=None)


def test_mcp_server_registers_all_tools(tmp_path):
    services, _, _ = _services(tmp_path)
    server = create_server(services)
    names = sorted(t.name for t in asyncio.run(server.list_tools()))
    assert names == [
        "delete_skill",
        "get_skill",
        "list_global_skills",
        "list_my_skills",
        "publish_skill",
        "search_skills",
        "update_skill",
    ]

    # call a real tool through the FastMCP runtime
    result = asyncio.run(server.call_tool("list_global_skills", {"limit": 5}))
    assert list(result)  # structured tool result returned
