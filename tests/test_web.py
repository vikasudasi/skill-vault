"""Hermetic tests for the server-rendered web dashboard."""

from __future__ import annotations

from pathlib import Path

from conftest import FakeEmbedder
from fastapi.testclient import TestClient

from skill_vault.auth import AuthService
from skill_vault.bootstrap import Services
from skill_vault.db import connect, run_migrations
from skill_vault.models import SkillInput
from skill_vault.search import SearchService, SqliteVecStore
from skill_vault.service import RegistryService
from skill_vault.trust import TrustService
from skill_vault.web.admin import AdminAuth
from skill_vault.web.app import create_app

MIGRATIONS = "/root/workspace/skill-vault/migrations"


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


def test_dashboard_requires_admin_auth(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    unauthenticated = client.get("/dashboard")
    assert unauthenticated.status_code == 401
    authenticated = client.get("/dashboard", auth=("t", "t"))
    assert authenticated.status_code == 200


def test_onboard_shows_key_once(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    response = client.post(
        "/dashboard/onboard",
        data={"name": "agent-one"},
        auth=("t", "t"),
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "sv_" in response.text
    assert "shown only once" in response.text.lower()


def test_admin_publish_visible_in_agent_dashboard(tmp_path: Path) -> None:
    client, services = _client(tmp_path)
    agent_id = services.auth.create_agent("owner")
    services.registry.admin_publish(agent_id, _skill("Planner"), "personal")
    page = client.get(f"/agents/{agent_id}", auth=("t", "t"))
    assert page.status_code == 200
    assert "Planner" in page.text


def test_skill_publish_update_delete_forms(tmp_path: Path) -> None:
    client, services = _client(tmp_path)
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
        auth=("t", "t"),
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
        auth=("t", "t"),
        follow_redirects=False,
    )
    assert edit.status_code == 303
    updated_page = client.get(f"/agents/{agent_id}", auth=("t", "t"))
    assert "Skill One Updated" in updated_page.text

    delete = client.post(
        f"/agents/{agent_id}/skills/{skill_id}/delete",
        auth=("t", "t"),
        follow_redirects=False,
    )
    assert delete.status_code == 303
    final_page = client.get(f"/agents/{agent_id}", auth=("t", "t"))
    assert "Skill One Updated" not in final_page.text


def test_global_browse_shows_results_and_badge(tmp_path: Path) -> None:
    client, services = _client(tmp_path)
    agent_id = services.auth.create_agent("publisher")
    services.registry.admin_publish(agent_id, _skill("Global Searchable"), "global")
    response = client.get("/browse?q=searchable&page=1")
    assert response.status_code == 200
    assert "Global Searchable" in response.text
    assert "badge-public" in response.text


def test_skill_detail_shows_metadata_without_body(tmp_path: Path) -> None:
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
    assert body not in response.text


def test_key_management_rotate_and_revoke(tmp_path: Path) -> None:
    client, services = _client(tmp_path)
    onboard = services.auth.onboard("key-agent")

    page = client.get(f"/agents/{onboard.agent_id}", auth=("t", "t"))
    assert page.status_code == 200
    assert onboard.key_prefix in page.text

    rotate = client.post(
        f"/agents/{onboard.agent_id}/keys/{onboard.key_id}/rotate",
        auth=("t", "t"),
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
        auth=("t", "t"),
        follow_redirects=False,
    )
    assert revoke.status_code == 303
    keys_after_revoke = services.auth.list_keys(onboard.agent_id)
    revoked = next(k for k in keys_after_revoke if k.key_id == active_key.key_id)
    assert revoked.revoked_at is not None
