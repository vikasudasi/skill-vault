"""Unit tests for the semantic search backend (Task 3).

Covers: text composition, real sqlite-vec ranking, delete, scope filtering for the
SearchService, empty-query handling, and reindex idempotency.
"""

from __future__ import annotations

import uuid

from conftest import FakeEmbedder, insert_agent, insert_skill_version

from skill_vault.search import (
    SearchService,
    SqliteVecStore,
    build_body_text,
    build_meta_text,
)


def _vec(index: int) -> list[float]:
    """384-d one-hot unit vector at ``index`` (deterministic, unit norm)."""
    v = [0.0] * 384
    v[index] = 1.0
    return v


# ---------------------------------------------------------------- text builders


def test_meta_text_composition():
    text = build_meta_text(
        type(
            "V",
            (),
            {
                "name": "docker",
                "description": "manage containers",
                "tags": ["devops", "cli"],
                "triggers": [],
                "meta_json": {},
            },
        )  # type: ignore[attr-defined]
    )
    assert "docker" in text
    assert "manage containers" in text
    assert "devops" in text


def test_body_text_prefix():
    body = "x" * 5000
    text = build_body_text(type("V", (), {"body": body}))  # type: ignore[attr-defined]
    assert len(text) < len(body)
    assert text.startswith("x")


# ------------------------------------------------------- real sqlite-vec store


def test_store_ranking_by_cosine(vec_db_path):
    store = SqliteVecStore(vec_db_path)
    a, b = _vec(0), _vec(1)
    store.upsert("v1", a, a)
    store.upsert("v2", b, b)
    results = store.query(a, a, top_k=2)
    assert results[0][0] == "v1"
    assert results[0][1] > results[1][1]


def test_store_delete(vec_db_path):
    store = SqliteVecStore(vec_db_path)
    store.upsert("v1", _vec(0), _vec(0))
    store.delete("v1")
    assert store.query(_vec(0), _vec(0), top_k=10) == []


# ------------------------------------------------------------- SearchService


def _svc(db, store, embedder) -> SearchService:
    return SearchService(db, store, embedder)


def test_search_global_only(db, fake_store, fake_embedder):
    insert_skill_version(db, name="docker", description="containers")
    insert_skill_version(db, name="k8s", description="orchestration")
    svc = _svc(db, fake_store, fake_embedder)
    svc.reindex_all()
    results = svc.search("anything")
    assert len(results) == 2


def test_search_excludes_other_agents_personal(db, fake_store, fake_embedder):
    agent_a = insert_agent(db, "a")
    insert_skill_version(db, name="global", description="g")
    _, version_b = insert_skill_version(
        db, name="secret", description="private to b", visibility="personal", owner_agent_id=agent_a
    )
    svc = _svc(db, fake_store, fake_embedder)
    svc.reindex_all()

    # 'all' scope: sees global + own personal
    all_results = svc.search("anything", owner_agent_id=agent_a, scope="all")
    assert len(all_results) == 2

    # a *different* agent must NOT see agent_a's personal skill
    other = insert_agent(db, "other")
    other_results = svc.search("anything", owner_agent_id=other, scope="all")
    ids = [vid for vid, _ in other_results]
    assert version_b not in ids


def test_search_personal_scope_only_own(db, fake_store, fake_embedder):
    agent_a = insert_agent(db, "a")
    insert_skill_version(db, name="global", description="g")
    _, version_b = insert_skill_version(
        db, name="secret", description="private", visibility="personal", owner_agent_id=agent_a
    )
    svc = _svc(db, fake_store, fake_embedder)
    svc.reindex_all()
    personal = svc.search("anything", owner_agent_id=agent_a, scope="personal")
    ids = [vid for vid, _ in personal]
    assert version_b in ids
    assert len(personal) == 1  # global excluded in personal scope


def test_search_requires_identity_for_personal(db, fake_store, fake_embedder):
    agent_a = insert_agent(db, "a")
    insert_skill_version(
        db, name="secret", description="x", visibility="personal", owner_agent_id=agent_a
    )
    svc = _svc(db, fake_store, fake_embedder)
    svc.reindex_all()
    # No identity -> cannot see any personal skills even in 'all' scope.
    results = svc.search("anything", owner_agent_id=None, scope="all")
    assert results == []


def test_search_team_scope_same_user_only(db, fake_store, fake_embedder):
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    db.execute(
        "INSERT INTO users(id, email, password_hash, superuser) VALUES (?, ?, ?, 0)",
        (user_a, "a@example.com", "hash-a"),
    )
    db.execute(
        "INSERT INTO users(id, email, password_hash, superuser) VALUES (?, ?, ?, 0)",
        (user_b, "b@example.com", "hash-b"),
    )

    owner = insert_agent(db, "owner")
    teammate = insert_agent(db, "teammate")
    outsider = insert_agent(db, "outsider")
    ownerless = insert_agent(db, "seed")
    db.execute("UPDATE agents SET owner_user_id = ? WHERE id = ?", (user_a, owner))
    db.execute("UPDATE agents SET owner_user_id = ? WHERE id = ?", (user_a, teammate))
    db.execute("UPDATE agents SET owner_user_id = ? WHERE id = ?", (user_b, outsider))
    db.commit()

    _, team_version = insert_skill_version(
        db,
        name="team-shared",
        description="shared with same user",
        visibility="team",
        owner_agent_id=owner,
    )
    _, global_version = insert_skill_version(
        db,
        name="global",
        description="visible to all scopes that include global",
    )
    svc = _svc(db, fake_store, fake_embedder)
    svc.reindex_all()

    same_user = svc.search(
        "anything",
        owner_agent_id=teammate,
        owner_user_id=user_a,
        scope="team",
    )
    assert {vid for vid, _ in same_user} == {team_version, global_version}

    other_user = svc.search(
        "anything",
        owner_agent_id=outsider,
        owner_user_id=user_b,
        scope="team",
    )
    assert {vid for vid, _ in other_user} == {global_version}

    ownerless_results = svc.search(
        "anything",
        owner_agent_id=ownerless,
        owner_user_id=None,
        scope="team",
    )
    assert ownerless_results == []


def test_search_all_includes_same_user_team(db, fake_store, fake_embedder):
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    db.execute(
        "INSERT INTO users(id, email, password_hash, superuser) VALUES (?, ?, ?, 0)",
        (user_a, "all-a@example.com", "hash-a"),
    )
    db.execute(
        "INSERT INTO users(id, email, password_hash, superuser) VALUES (?, ?, ?, 0)",
        (user_b, "all-b@example.com", "hash-b"),
    )

    owner = insert_agent(db, "owner")
    same_user_other_agent = insert_agent(db, "owner-peer")
    outsider = insert_agent(db, "outsider")
    db.execute("UPDATE agents SET owner_user_id = ? WHERE id = ?", (user_a, owner))
    db.execute("UPDATE agents SET owner_user_id = ? WHERE id = ?", (user_a, same_user_other_agent))
    db.execute("UPDATE agents SET owner_user_id = ? WHERE id = ?", (user_b, outsider))
    db.commit()

    _, own_personal = insert_skill_version(
        db,
        name="own-personal",
        description="owner private",
        visibility="personal",
        owner_agent_id=owner,
    )
    _, same_user_team = insert_skill_version(
        db,
        name="same-user-team",
        description="team shared",
        visibility="team",
        owner_agent_id=same_user_other_agent,
    )
    _, other_user_team = insert_skill_version(
        db,
        name="other-user-team",
        description="should be hidden",
        visibility="team",
        owner_agent_id=outsider,
    )
    _, global_version = insert_skill_version(db, name="global", description="g")

    svc = _svc(db, fake_store, fake_embedder)
    svc.reindex_all()
    results = svc.search("anything", owner_agent_id=owner, owner_user_id=user_a, scope="all")
    ids = {vid for vid, _ in results}
    assert own_personal in ids
    assert same_user_team in ids
    assert global_version in ids
    assert other_user_team not in ids


def test_empty_query_returns_empty(db, fake_store, fake_embedder):
    insert_skill_version(db, name="docker", description="containers")
    svc = _svc(db, fake_store, fake_embedder)
    svc.reindex_all()
    assert svc.search("") == []


def test_reindex_idempotent(db, vec_db_path):
    insert_skill_version(db, name="a", description="x")
    insert_skill_version(db, name="b", description="y")
    store = SqliteVecStore(vec_db_path)
    svc = _svc(db, store, FakeEmbedder())
    first = svc.reindex_all()
    second = svc.reindex_all()
    assert first == 2
    assert second == 2
