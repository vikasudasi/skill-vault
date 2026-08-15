"""Unit tests for the Qdrant vector backend (local embedded mode, no network)."""

from __future__ import annotations

import pytest

from skill_vault.search import QdrantVectorStore, build_store

GLOBAL_A = "00000000-0000-0000-0000-000000000001"
GLOBAL_B = "00000000-0000-0000-0000-000000000002"
PERSONAL = "00000000-0000-0000-0000-000000000003"


def _vec(index: int) -> list[float]:
    """384-d one-hot unit vector at ``index`` (deterministic, unit norm)."""
    v = [0.0] * 384
    v[index] = 1.0
    return v


@pytest.fixture
def store(tmp_path):
    return QdrantVectorStore(path=str(tmp_path / "qdrant_data"))


def test_upsert_and_query_returns_ranked_ids(store):
    a, b = _vec(0), _vec(1)
    store.upsert(GLOBAL_A, a, a, visibility="global")
    store.upsert(GLOBAL_B, b, b, visibility="global")
    results = store.query(a, a, top_k=2)
    assert results[0][0] == GLOBAL_A
    assert results[0][1] > results[1][1]


def test_query_filter_excludes_non_global(store):
    store.upsert(GLOBAL_A, _vec(0), _vec(0), visibility="global")
    store.upsert(PERSONAL, _vec(0), _vec(0), visibility="personal", owner_agent_id="agent-x")
    results = store.query(_vec(0), _vec(0), top_k=10, filter={"visibility": "global"})
    assert [vid for vid, _ in results] == [GLOBAL_A]


def test_delete_removes_points(store):
    store.upsert(GLOBAL_A, _vec(0), _vec(0), visibility="global")
    store.delete(GLOBAL_A)
    assert store.query(_vec(0), _vec(0), top_k=10) == []


def test_build_store_qdrant(tmp_path):
    store = build_store("qdrant", "unused.db", qdrant_path=str(tmp_path / "qd"))
    assert isinstance(store, QdrantVectorStore)
