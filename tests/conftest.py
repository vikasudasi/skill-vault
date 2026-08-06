"""Shared pytest fixtures for Skill Vault — hermetic (temp DB, fakes, no real model)."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

from skill_vault.db import connect, run_migrations
from skill_vault.search import VectorStore

# The admin password is now a required secret (config.py raises without it).
# Provide a known test value now so every test that reaches get_settings()
# (or create_app -> build_services) runs without a real secret. Tests that
# specifically cover config override it via monkeypatch + cache_clear.
os.environ.setdefault("SKILL_VAULT_ADMIN_PASSWORD", "test-admin-password")

MIGRATIONS_DIR = str(Path(__file__).resolve().parent.parent / "migrations")


@pytest.fixture
def db(tmp_path):
    """A temp SQLite DB with the baseline schema applied."""
    path = str(tmp_path / "test.db")
    conn = connect(path)
    run_migrations(conn, MIGRATIONS_DIR)
    yield conn
    conn.close()


@pytest.fixture
def vec_db_path(tmp_path):
    """A separate temp DB path for the sqlite-vec store."""
    return str(tmp_path / "vec.db")


def insert_agent(db, name: str = "agent") -> str:
    aid = str(uuid.uuid4())
    db.execute("INSERT INTO agents(id, name) VALUES (?, ?)", (aid, name))
    db.commit()
    return aid


def insert_skill_version(
    db,
    *,
    name: str,
    description: str,
    body: str = "body text",
    visibility: str = "global",
    owner_agent_id: str | None = None,
    tags: list[str] | None = None,
    triggers: list[str] | None = None,
) -> tuple[str, str]:
    """Insert a skill + its first version; returns ``(skill_id, version_id)``."""
    sid = str(uuid.uuid4())
    vid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO skills(id, name, owner_agent_id, visibility) VALUES (?, ?, ?, ?)",
        (sid, name, owner_agent_id, visibility),
    )
    db.execute(
        "INSERT INTO skill_versions(id, skill_id, version, content_hash, name, description, "
        "tags, triggers, meta_json, body) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?)",
        (
            vid,
            sid,
            "a" * 64,
            name,
            description,
            json.dumps(tags or []),
            json.dumps(triggers or []),
            "{}",
            body,
        ),
    )
    db.execute("UPDATE skills SET current_version_id = ? WHERE id = ?", (vid, sid))
    db.commit()
    return sid, vid


class FakeEmbedder:
    """Deterministic embedder that returns a fixed 384-d unit vector (no model load)."""

    def __init__(self) -> None:
        self.embed_calls = 0

    def embed(self, text: str) -> list[float]:
        self.embed_calls += 1
        return [0.0] * 383 + [1.0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.embed_calls += len(texts)
        return [self.embed(t) for t in texts]


class FakeStore(VectorStore):
    """In-memory dict store; query returns items in insertion order (isolates scope logic)."""

    def __init__(self) -> None:
        super().__init__()
        self._items: dict[str, tuple[list[float], list[float]]] = {}
        self._order: list[str] = []

    def upsert(self, version_id: str, meta: list[float], body: list[float]) -> None:
        if version_id not in self._items:
            self._order.append(version_id)
        self._items[version_id] = (meta, body)

    def delete(self, version_id: str) -> None:
        self._items.pop(version_id, None)
        if version_id in self._order:
            self._order.remove(version_id)

    def query(
        self,
        meta: list[float],
        body: list[float],
        top_k: int,
    ) -> list[tuple[str, float]]:
        return [(vid, 1.0) for vid in self._order][:top_k]


@pytest.fixture
def fake_embedder():
    return FakeEmbedder()


@pytest.fixture
def fake_store():
    return FakeStore()
