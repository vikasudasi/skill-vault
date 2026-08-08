"""Header-based MCP auth resolution (Task: standardize auth source).

Covers the ``tools._resolve_agent_key`` / ``tools._header_agent_key`` resolver:
precedence (explicit per-call arg wins), header parsing (Authorization: Bearer +
X-Agent-Key, case-insensitive), and absence handling (no request context, no
header -> guest). Simulates request headers via monkeypatched
``fastmcp.server.dependencies.get_http_request`` with a minimal fake request.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from conftest import FakeEmbedder

from skill_vault.auth import AuthService
from skill_vault.bootstrap import Services
from skill_vault.db import connect, run_migrations
from skill_vault.models import SkillInput
from skill_vault.search import SearchService, SqliteVecStore
from skill_vault.server import create_server
from skill_vault.service import RegistryService
from skill_vault.tools import _header_agent_key, _resolve_agent_key
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


@pytest.fixture
def stack(tmp_path):
    return _stack(tmp_path)


class _FakeRequest:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = {k.lower(): v for k, v in headers.items()}


@pytest.fixture
def fake_http(monkeypatch):
    """Patches get_http_request to return the given request (or raise)."""

    def _set(request, *, raise_error=False):
        if raise_error:

            def _boom():
                raise RuntimeError("No active HTTP request found.")

            monkeypatch.setattr("fastmcp.server.dependencies.get_http_request", _boom)
            return

        monkeypatch.setattr("fastmcp.server.dependencies.get_http_request", lambda: request)

    return _set


# -- _header_agent_key parsing -----------------------------------------------


def test_header_bearer_authorization(fake_http):
    fake_http(_FakeRequest({"Authorization": "Bearer secret-key-123"}))
    assert _header_agent_key() == "secret-key-123"


def test_header_bearer_lowercase_prefix(fake_http):
    fake_http(_FakeRequest({"authorization": "bearer  sk-abc"}))
    assert _header_agent_key() == "sk-abc"


def test_header_x_agent_key(fake_http):
    fake_http(_FakeRequest({"X-Agent-Key": "key-from-xheader"}))
    assert _header_agent_key() == "key-from-xheader"


def test_header_x_agent_key_case_insensitive(fake_http):
    fake_http(_FakeRequest({"x-agent-key": "key-lower"}))
    assert _header_agent_key() == "key-lower"


def test_header_bearer_precedes_x_agent_key(fake_http):
    fake_http(_FakeRequest({"Authorization": "Bearer primary-key", "X-Agent-Key": "fallback-key"}))
    assert _header_agent_key() == "primary-key"


def test_header_authorization_non_bearer_ignored(fake_http):
    # 'Basic dXNlcg==' style auth header must not be treated as a bearer key
    fake_http(_FakeRequest({"Authorization": "Basic dXNlcg=="}))
    assert _header_agent_key() is None


def test_header_missing_and_invalid_returns_none(fake_http):
    fake_http(_FakeRequest({}))
    assert _header_agent_key() is None
    fake_http(_FakeRequest({"Authorization": "Bearer   "}))  # blank token
    assert _header_agent_key() is None
    fake_http(_FakeRequest({"X-Agent-Key": "   "}))  # blank alt header
    assert _header_agent_key() is None


def test_header_no_request_context_returns_none(fake_http):
    fake_http(None, raise_error=True)
    assert _header_agent_key() is None


# -- _resolve_agent_key precedence -------------------------------------------


def test_resolve_explicit_arg_overrides_header(fake_http):
    fake_http(_FakeRequest({"Authorization": "Bearer header-key"}))
    assert _resolve_agent_key("explicit-arg-key") == "explicit-arg-key"


def test_resolve_header_used_when_no_arg(fake_http):
    fake_http(_FakeRequest({"X-Agent-Key": "header-key"}))
    assert _resolve_agent_key(None) == "header-key"


def test_resolve_guest_when_nothing_present(fake_http):
    fake_http(_FakeRequest({}))
    assert _resolve_agent_key(None) is None


# -- integration: tool with explicit key still works --------------------------
# Reuse the hermetic stack builder pattern from test_tools.py.


def test_tool_explicit_key_still_works(stack):
    server, _, auth = stack
    onboard = auth.onboard("wally")
    skill = SkillInput(
        name="mcp-auth",
        description="mcp auth test skill",
        tags=["test"],
        triggers=["auth"],
        body="# mcp-auth\nheader auth integration",
        meta={},
    )
    res = asyncio.run(
        server.call_tool(
            "publish_skill",
            {"skill": skill, "visibility": "personal", "agent_key": onboard.raw_key},
        )
    )
    out = str(next(iter(res)))
    assert "version" in out or "id" in out
