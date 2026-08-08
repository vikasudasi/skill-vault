"""Hermetic tests for the server-rendered web dashboard."""

from __future__ import annotations

from pathlib import Path

from conftest import FakeEmbedder
from fastapi.testclient import TestClient

from skill_vault.auth import AuthService
from skill_vault.bootstrap import Services
from skill_vault.config import get_settings
from skill_vault.db import connect, run_migrations
from skill_vault.models import SkillInput
from skill_vault.search import SearchService, SqliteVecStore
from skill_vault.service import RegistryService
from skill_vault.trust import TrustService
from skill_vault.web.admin import AdminAuth
from skill_vault.web.app import create_app

MIGRATIONS = str(Path(__file__).resolve().parent.parent / "migrations")


def _services(tmp_path: Path) -> Services:
    db = connect(str(tmp_path / "app.db"))
    run_migrations(db, MIGRATIONS)
    auth = AuthService(db, rate_limit=100000)
    store = SqliteVecStore(str(tmp_path / "vec.db"))
    search = SearchService(db, store, FakeEmbedder())
    trust = TrustService(db, allow_tiers=("verified", "user", "public"))
    registry = RegistryService(db, auth=auth, search=search, trust=trust)
    return Services(db=db, auth=auth, search=search, trust=trust, registry=registry)


def _client(tmp_path: Path) -> tuple[TestClient, Services]:
    services = _services(tmp_path)
    app = create_app(
        services=services,
        admin=AdminAuth("t", "t", verify=lambda user, password: user == "t" and password == "t"),
    )
    return TestClient(app), services


def _authed_client(
    tmp_path: Path,
    email: str = "engineer@skillvault.dev",
    password: str = "password123",
    *,
    superuser: bool = True,
) -> tuple[TestClient, Services]:
    """Return a client logged in via the session-cookie auth flow.

    Creates a user through AuthService (so we control the superuser flag directly),
    then logs them in through the real POST /login route so the client carries the
    httpOnly session cookie that the dashboard routes require.
    """
    client, services = _client(tmp_path)
    services.auth.create_user(email, password, superuser=1 if superuser else 0)
    login = client.post(
        "/login", data={"email": email, "password": password}, follow_redirects=False
    )
    assert login.status_code == 302, login.text
    assert "sv_session" in client.cookies
    return client, services


def _skill(name: str, body: str = "sample body", description: str | None = None) -> SkillInput:
    return SkillInput(
        name=name,
        description=description or f"{name} description",
        tags=["tag-a", "tag-b"],
        triggers=["when needed"],
        body=body,
        meta={},
    )


def test_healthz(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_public_routes_render_html(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    homepage = client.get("/")
    configure = client.get("/configure")
    assert homepage.status_code == 200
    assert configure.status_code == 200
    assert homepage.headers["content-type"].startswith("text/html")
    assert configure.headers["content-type"].startswith("text/html")


def test_homepage_contains_core_pitch_and_links(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    response = client.get("/")
    assert response.status_code == 200
    page = response.text
    assert "Skill Vault" in page
    assert "One MCP endpoint" in page
    assert "Per-agent private vaults" in page
    assert "Verified supply chain" in page
    assert 'href="/configure"' in page
    assert 'href="/dashboard"' in page


def test_configure_page_contains_verified_transport_snippets(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    response = client.get("/configure")
    assert response.status_code == 200
    page = response.text
    assert "stdio" in page.lower()
    assert "streamable-http" in page
    assert "--transport streamable-http" in page
    assert "/mcp" in page
    assert "Claude Code" in page
    assert "Cursor" in page
    assert "Codex" in page
    assert "Gemini CLI" in page
    assert "agent_key" in page


def test_public_pages_do_not_require_admin_auth(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    assert client.get("/").status_code == 200
    assert client.get("/configure").status_code == 200


def test_browse_header_shows_logout_when_logged_in(tmp_path: Path) -> None:
    client, _ = _authed_client(tmp_path)
    page = client.get("/browse")
    assert page.status_code == 200
    # The user is logged in, so the header must show Logout / not Login+Sign up
    assert "Logout" in page.text
    assert 'href="/login"' not in page.text
    assert 'href="/signup"' not in page.text


def test_homepage_replaces_wildcard_host(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SKILL_VAULT_WEB_HOST", "0.0.0.0")
    monkeypatch.setenv("SKILL_VAULT_WEB_PORT", "8000")
    get_settings.cache_clear()
    try:
        client, _ = _client(tmp_path)
        response = client.get("/")
        assert response.status_code == 200
        assert "your-host-or-ip" in response.text
        assert "0.0.0.0" not in response.text
    finally:
        get_settings.cache_clear()


def test_dashboard_requires_login(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    unauthenticated = client.get("/dashboard", follow_redirects=False)
    assert unauthenticated.status_code == 302
    assert unauthenticated.headers["location"].startswith("/login")
    authed, _ = _authed_client(tmp_path)
    assert authed.get("/dashboard").status_code == 200


def test_onboard_shows_key_once(tmp_path: Path) -> None:
    client, _ = _authed_client(tmp_path)
    response = client.post(
        "/dashboard/onboard",
        data={"name": "agent-one"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "sv_" in response.text
    assert "shown only once" in response.text.lower()


def test_admin_publish_visible_in_agent_dashboard(tmp_path: Path) -> None:
    client, services = _authed_client(tmp_path)
    agent_id = services.auth.create_agent("owner")
    services.registry.admin_publish(agent_id, _skill("Planner"), "personal")
    page = client.get(f"/agents/{agent_id}")
    assert page.status_code == 200
    assert "Planner" in page.text


def test_skill_publish_update_delete_forms(tmp_path: Path) -> None:
    client, services = _authed_client(tmp_path)
    agent_id = services.auth.create_agent("agent-a")
    publish = client.post(
        f"/agents/{agent_id}/skills",
        data={
            "name": "Skill One",
            "description": "Initial description",
            "tags": "ops,deploy",
            "triggers": "release",
            "body": "initial body",
            "visibility": "personal",
        },
        follow_redirects=False,
    )
    assert publish.status_code == 303
    cards = services.registry.admin_list_my(agent_id)
    assert len(cards) == 1
    skill_id = cards[0].id

    edit = client.post(
        f"/agents/{agent_id}/skills/{skill_id}",
        data={
            "name": "Skill One Updated",
            "description": "Updated description",
            "tags": "ops,deploy",
            "triggers": "release",
            "body": "updated body",
        },
        follow_redirects=False,
    )
    assert edit.status_code == 303
    updated_page = client.get(f"/agents/{agent_id}")
    assert "Skill One Updated" in updated_page.text

    delete = client.post(
        f"/agents/{agent_id}/skills/{skill_id}/delete",
        follow_redirects=False,
    )
    assert delete.status_code == 303
    final_page = client.get(f"/agents/{agent_id}")
    assert "Skill One Updated" not in final_page.text


def test_new_skill_form_and_edit_preserve_team_visibility(tmp_path: Path) -> None:
    client, services = _authed_client(tmp_path)
    user_id = services.db.execute(
        "SELECT id FROM users WHERE email = ?",
        ("engineer@skillvault.dev",),
    ).fetchone()["id"]
    onboarded = services.auth.onboard("team-owner", owner_user_id=str(user_id))

    form_page = client.get(f"/agents/{onboarded.agent_id}/skills/new")
    assert form_page.status_code == 200
    assert 'value="team"' in form_page.text

    published = services.registry.admin_publish(onboarded.agent_id, _skill("Team Skill"), "team")
    edit_page = client.get(f"/agents/{onboarded.agent_id}/skills/{published.id}/edit")
    assert edit_page.status_code == 200
    assert 'value="team" checked' in edit_page.text


def test_global_browse_shows_results_and_badge(tmp_path: Path) -> None:
    client, services = _client(tmp_path)
    agent_id = services.auth.create_agent("publisher")
    services.registry.admin_publish(agent_id, _skill("Global Searchable"), "global")
    response = client.get("/browse?q=searchable&page=1")
    assert response.status_code == 200
    assert "Global Searchable" in response.text
    assert "badge-public" in response.text


def test_browse_hides_confidence_without_query_shows_with_query(tmp_path: Path) -> None:
    from skill_vault.models import SkillCard

    client, services = _client(tmp_path)
    agent_id = services.auth.create_agent("publisher")
    services.registry.admin_publish(agent_id, _skill("Global Searchable"), "global")

    # browsing with no query -> list_global yields score=0 -> no misleading 0%
    empty = client.get("/browse")
    assert empty.status_code == 200
    assert "Global Searchable" in empty.text
    assert "confidence" not in empty.text

    # during an actual search the relevance confidence IS shown
    services.registry.search = lambda *a, **k: [
        SkillCard(
            id="x",
            name="Global Searchable",
            description="d",
            tags=[],
            trust="public",
            score=0.85,
            version=1,
        )
    ]
    with_q = client.get("/browse?q=whatever")
    assert with_q.status_code == 200
    assert "confidence" in with_q.text
    assert "85%" in with_q.text


def test_browse_fragment_hides_confidence_without_query_shows_with_query(
    tmp_path: Path,
) -> None:
    """The HTMX fragment must preserve the trust badge and the score-gated
    confidence line exactly like the full page."""
    from skill_vault.models import SkillCard

    client, services = _client(tmp_path)
    agent_id = services.auth.create_agent("publisher")
    services.registry.admin_publish(agent_id, _skill("Global Searchable"), "global")

    empty = client.get("/browse?partial=1")
    assert empty.status_code == 200
    assert "Global Searchable" in empty.text
    assert "badge-public" in empty.text
    assert "confidence" not in empty.text

    services.registry.search = lambda *a, **k: [
        SkillCard(
            id="x",
            name="Global Searchable",
            description="d",
            tags=[],
            trust="public",
            score=0.85,
            version=1,
        )
    ]
    with_q = client.get("/browse?q=whatever&partial=1")
    assert with_q.status_code == 200
    assert "confidence" in with_q.text
    assert "85%" in with_q.text


def test_browse_hx_request_returns_fragment_not_full_page(tmp_path: Path) -> None:
    """htmx sends the HX-Request header; /browse must then return only the
    results fragment (no <html>/<head>/<body> shell), while a request without
    the header keeps returning the full page."""
    client, services = _client(tmp_path)
    agent_id = services.auth.create_agent("publisher")
    services.registry.admin_publish(agent_id, _skill("Global Searchable"), "global")

    # Full page carries the shell (header nav) and the search form.
    full = client.get("/browse")
    assert full.status_code == 200
    assert "<html" in full.text
    assert 'href="/browse"' in full.text  # search form action

    # HX-Request -> fragment only.
    partial = client.get("/browse", headers={"HX-Request": "true"})
    assert partial.status_code == 200
    assert "Global Searchable" in partial.text
    assert "badge-public" in partial.text
    assert "<html" not in partial.text
    assert "<header" not in partial.text
    assert 'id="search-form"' not in partial.text  # no search-form shell


def test_browse_partial_pagination_links(tmp_path: Path) -> None:
    """The fragment pager targets #results so an htmx request swaps only the
    results container (no full reload) and uses hx-push-url."""
    client, services = _client(tmp_path)
    agent_id = services.auth.create_agent("publisher")
    for n in range(12):
        services.registry.admin_publish(
            agent_id, _skill(f"Global Skill {n}", description=f"desc {n}"), "global"
        )

    partial = client.get("/browse?page=2&partial=1")
    assert partial.status_code == 200
    assert 'hx-target="#results"' in partial.text
    assert 'hx-push-url="true"' in partial.text


def test_skill_detail_shows_metadata_and_body(tmp_path: Path) -> None:
    client, services = _client(tmp_path)
    agent_id = services.auth.create_agent("publisher")
    body = "TOP SECRET BODY CONTENT"
    result = services.registry.admin_publish(
        agent_id,
        _skill("Visible Metadata", body=body),
        "global",
    )
    response = client.get(f"/skills/{result.id}")
    assert response.status_code == 200
    assert "Visible Metadata" in response.text
    assert "Integrity" in response.text
    assert body in response.text
    assert "Skill file" in response.text


def test_key_management_rotate_and_revoke(tmp_path: Path) -> None:
    client, services = _authed_client(tmp_path)
    onboard = services.auth.onboard("key-agent")

    page = client.get(f"/agents/{onboard.agent_id}")
    assert page.status_code == 200
    assert onboard.key_prefix in page.text

    rotate = client.post(
        f"/agents/{onboard.agent_id}/keys/{onboard.key_id}/rotate",
        follow_redirects=False,
    )
    assert rotate.status_code == 200
    assert "shown only once" in rotate.text.lower()
    assert "sv_" in rotate.text

    keys_after_rotate = services.auth.list_keys(onboard.agent_id)
    old_key = next(k for k in keys_after_rotate if k.key_id == onboard.key_id)
    assert old_key.revoked_at is not None
    active_keys = [k for k in keys_after_rotate if k.revoked_at is None]
    assert len(active_keys) == 1
    active_key = active_keys[0]

    revoke = client.post(
        f"/agents/{onboard.agent_id}/keys/{active_key.key_id}/revoke",
        follow_redirects=False,
    )
    assert revoke.status_code == 303
    keys_after_revoke = services.auth.list_keys(onboard.agent_id)
    revoked = next(k for k in keys_after_revoke if k.key_id == active_key.key_id)
    assert revoked.revoked_at is not None


# -- user signup / login / logout / ownership scoping ------------------------


def test_signup_creates_user_and_sets_session(tmp_path: Path) -> None:
    client, services = _client(tmp_path)
    resp = client.post(
        "/signup",
        data={
            "email": "New.User@Example.com",
            "password": "hunter2password",
            "confirm_password": "hunter2password",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard"
    assert "sv_session" in client.cookies
    row = services.db.execute(
        "SELECT * FROM users WHERE email = ?", ("new.user@example.com",)
    ).fetchone()
    assert row is not None
    assert row["superuser"] == 0
    assert "hunter2password" not in row["password_hash"]
    assert "$" in row["password_hash"]  # pbkdf2 record


def test_signup_rejects_invalid_and_duplicate(tmp_path: Path) -> None:
    client, services = _client(tmp_path)
    bad = client.post(
        "/signup",
        data={"email": "not-an-email", "password": "short", "confirm_password": "short"},
    )
    assert bad.status_code == 400
    assert "valid email" in bad.text.lower()

    services.auth.create_user("dup@example.com", "password123")
    dup = client.post(
        "/signup",
        data={
            "email": "dup@example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert dup.status_code == 400
    assert "already exists" in dup.text.lower()


def test_login_success_and_failure(tmp_path: Path) -> None:
    client, services = _client(tmp_path)
    services.auth.create_user("login@example.com", "password123")
    ok = client.post(
        "/login",
        data={"email": "login@example.com", "password": "password123"},
        follow_redirects=False,
    )
    assert ok.status_code == 302
    assert ok.headers["location"] == "/dashboard"
    assert "sv_session" in client.cookies

    bad = client.post("/login", data={"email": "login@example.com", "password": "WRONG"})
    assert bad.status_code == 401
    assert "Invalid email or password" in bad.text


def test_logout_clears_session(tmp_path: Path) -> None:
    client, _ = _authed_client(tmp_path)
    assert client.get("/dashboard").status_code == 200
    out = client.post("/logout", follow_redirects=False)
    assert out.status_code == 302
    assert "sv_session" not in client.cookies
    assert client.get("/dashboard", follow_redirects=False).status_code == 302


def test_user_sees_only_own_agents(tmp_path: Path) -> None:
    # Owner A has one agent; owner B must not see it.
    services = _services(tmp_path)
    app = create_app(
        services=services,
        admin=AdminAuth("t", "t", verify=lambda u, p: u == "t" and p == "t"),
    )
    client_a, client_b = TestClient(app), TestClient(app)
    services.auth.create_user("a@example.com", "password123")
    services.auth.create_user("b@example.com", "password123")
    a_login = client_a.post(
        "/login", data={"email": "a@example.com", "password": "password123"}, follow_redirects=False
    )
    b_login = client_b.post(
        "/login", data={"email": "b@example.com", "password": "password123"}, follow_redirects=False
    )
    assert a_login.status_code == 302 and b_login.status_code == 302

    a_id = services.db.execute("SELECT id FROM users WHERE email='a@example.com'").fetchone()["id"]
    b_id = services.db.execute("SELECT id FROM users WHERE email='b@example.com'").fetchone()["id"]
    agent_a = services.auth.onboard("agent-owner-a", owner_user_id=a_id)
    agent_b = services.auth.onboard("agent-owner-b", owner_user_id=b_id)

    # A can see own agent, not B's.
    assert client_a.get(f"/agents/{agent_a.agent_id}").status_code == 200
    assert client_a.get(f"/agents/{agent_b.agent_id}").status_code == 404
    # Public read of a global skill is unaffected, but B's private agent is hidden.
    assert client_a.get("/browse").status_code == 200


def test_superuser_sees_all_agents(tmp_path: Path) -> None:
    client, services = _authed_client(tmp_path, superuser=True)
    # ownerless (seed/system) agent
    nobody = services.auth.create_agent("seed-agent")
    page = client.get(f"/agents/{nobody}")
    assert page.status_code == 200


def test_superuser_toggles_super_agent_flag(tmp_path: Path) -> None:
    client, services = _authed_client(tmp_path, superuser=True)
    agent_id = services.auth.create_agent("toggle-me")
    assert (
        services.db.execute(
            "SELECT is_super_agent FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()["is_super_agent"]
        == 0
    )

    promote = client.post(
        f"/agents/{agent_id}/super", data={"is_super": "1"}, follow_redirects=False
    )
    assert promote.status_code == 303
    assert (
        services.db.execute(
            "SELECT is_super_agent FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()["is_super_agent"]
        == 1
    )

    demote = client.post(
        f"/agents/{agent_id}/super", data={"is_super": "0"}, follow_redirects=False
    )
    assert demote.status_code == 303
    assert (
        services.db.execute(
            "SELECT is_super_agent FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()["is_super_agent"]
        == 0
    )


def test_non_superuser_cannot_toggle_super_agent_flag(tmp_path: Path) -> None:
    client, services = _authed_client(tmp_path, superuser=False)
    agent_id = services.auth.create_agent("protected")
    response = client.post(f"/agents/{agent_id}/super", data={"is_super": 1})
    assert response.status_code == 403
    assert (
        services.db.execute(
            "SELECT is_super_agent FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()["is_super_agent"]
        == 0
    )


# -- delete agent ------------------------------------------------------------


def _agent_owned_by_user(services, user_id: str, name: str) -> str:
    return services.auth.onboard(name, owner_user_id=user_id).agent_id


def test_delete_agent_success(tmp_path: Path) -> None:
    client, services = _authed_client(tmp_path)
    user_id = services.db.execute(
        "SELECT id FROM users WHERE email = ?", ("engineer@skillvault.dev",)
    ).fetchone()["id"]
    agent_id = _agent_owned_by_user(services, user_id, "doomed-agent")

    response = client.post(f"/agents/{agent_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    assert services.db.execute("SELECT 1 FROM agents WHERE id = ?", (agent_id,)).fetchone() is None


def test_delete_agent_last_agent_blocked(tmp_path: Path) -> None:
    client, services = _authed_client(tmp_path, superuser=False)
    user_id = services.db.execute(
        "SELECT id FROM users WHERE email = ?", ("engineer@skillvault.dev",)
    ).fetchone()["id"]
    agent_id = _agent_owned_by_user(services, user_id, "only-agent")

    response = client.post(f"/agents/{agent_id}/delete", follow_redirects=False)
    assert response.status_code == 403
    # Agent still exists.
    assert (
        services.db.execute("SELECT 1 FROM agents WHERE id = ?", (agent_id,)).fetchone() is not None
    )


def test_delete_agent_non_owner_forbidden(tmp_path: Path) -> None:
    # Owner B has an agent; non-superuser A must not be able to delete it.
    services = _services(tmp_path)
    app = create_app(
        services=services,
        admin=AdminAuth("t", "t", verify=lambda u, p: u == "t" and p == "t"),
    )
    client_owner, client_other = TestClient(app), TestClient(app)
    services.auth.create_user("owner@example.com", "password123")
    services.auth.create_user("other@example.com", "password123")
    owner_login = client_owner.post(
        "/login",
        data={"email": "owner@example.com", "password": "password123"},
        follow_redirects=False,
    )
    other_login = client_other.post(
        "/login",
        data={"email": "other@example.com", "password": "password123"},
        follow_redirects=False,
    )
    assert owner_login.status_code == 302 and other_login.status_code == 302
    owner_id = services.db.execute(
        "SELECT id FROM users WHERE email = 'owner@example.com'"
    ).fetchone()["id"]
    agent_id = _agent_owned_by_user(services, owner_id, "private-agent")

    # Non-owner gets 404 (route hides the agent entirely, like other agent routes).
    response = client_other.post(f"/agents/{agent_id}/delete", follow_redirects=False)
    assert response.status_code == 404
    assert (
        services.db.execute("SELECT 1 FROM agents WHERE id = ?", (agent_id,)).fetchone() is not None
    )

    # Superuser may delete any agent.
    services.auth.upsert_superuser("root@example.com", "password123")
    client_root = TestClient(app)
    root_login = client_root.post(
        "/login",
        data={"email": "root@example.com", "password": "password123"},
        follow_redirects=False,
    )
    assert root_login.status_code == 302
    root_response = client_root.post(f"/agents/{agent_id}/delete", follow_redirects=False)
    assert root_response.status_code == 303
    assert services.db.execute("SELECT 1 FROM agents WHERE id = ?", (agent_id,)).fetchone() is None


def test_delete_agent_cascades_owned_skills(tmp_path: Path) -> None:
    client, services = _authed_client(tmp_path)
    user_id = services.db.execute(
        "SELECT id FROM users WHERE email = ?", ("engineer@skillvault.dev",)
    ).fetchone()["id"]
    agent_id = _agent_owned_by_user(services, user_id, "cascade-agent")
    second_agent = _agent_owned_by_user(services, user_id, "survivor-agent")

    # Owner publishes personal + team skills owned by the doomed agent.
    personal = services.registry.admin_publish(agent_id, _skill("Personal Tactic"), "personal")
    team = services.registry.admin_publish(agent_id, _skill("Team Playbook"), "team")
    # A global skill owned by the doomed agent (published via superuser admin path).
    global_skill = services.registry.admin_publish(agent_id, _skill("Global Note"), "global")

    response = client.post(f"/agents/{agent_id}/delete", follow_redirects=False)
    assert response.status_code == 303

    # All owned skills are gone — skills, versions, and trust records cascade.
    for sid in (personal.id, team.id, global_skill.id):
        assert services.db.execute("SELECT 1 FROM skills WHERE id = ?", (sid,)).fetchone() is None
        assert (
            services.db.execute(
                "SELECT 1 FROM skill_versions WHERE skill_id = ?", (sid,)
            ).fetchone()
            is None
        )
    trust_rows = services.db.execute(
        "SELECT COUNT(*) AS c FROM trust WHERE skill_version_id = ?", (personal.id,)
    ).fetchone()["c"]
    assert trust_rows == 0

    # The survivor agent + its own skills remain.
    assert (
        services.db.execute("SELECT 1 FROM agents WHERE id = ?", (second_agent,)).fetchone()
        is not None
    )
