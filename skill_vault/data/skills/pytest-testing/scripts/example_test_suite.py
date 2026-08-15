#!/usr/bin/env python3
"""Pragmatic pytest suite demonstrating fixtures, parametrize, tmp_path, and marks."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


# - Fixtures -


@pytest.fixture(scope="function")
def db(tmp_path: Path):
    """Isolated SQLite DB per test - Skill Vault pattern."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE skills (id INTEGER PRIMARY KEY, name TEXT UNIQUE)")
    conn.execute("INSERT INTO skills (name) VALUES ('pytest'), ('asyncio')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def shared_config():
    """Module-scoped fixture: expensive to create, reused across test functions."""
    return {"app_name": "skill-vault", "max_skills": 1000}


# - Test functions -


def test_db_has_rows(db):
    """Fixture provides isolated DB - no cross-test contamination."""
    rows = db.execute("SELECT COUNT(*) FROM skills").fetchone()
    assert rows[0] == 2


def test_db_insert(db):
    db.execute("INSERT INTO skills (name) VALUES ('coverage')")
    db.commit()
    rows = db.execute("SELECT COUNT(*) FROM skills").fetchone()
    assert rows[0] == 3


def test_config_is_module_scoped(shared_config):
    assert shared_config["app_name"] == "skill-vault"


# - Parametrize -


@pytest.mark.parametrize(
    "name,expected_count",
    [
        ("pytest", 1),  # existing
        ("asyncio", 1),  # existing
        ("missing", 0),  # edge: not found
        ("", 0),  # edge: empty string
    ],
    ids=["found-1", "found-2", "missing", "empty"],
)
def test_skill_lookup(db, name, expected_count):
    rows = db.execute("SELECT COUNT(*) FROM skills WHERE name = ?", (name,)).fetchone()
    assert rows[0] == expected_count


# - Marks -


@pytest.mark.slow
def test_expensive_operation():
    """Marked as slow - CI can skip with `-m 'not slow'`."""
    import time

    time.sleep(0.1)
    assert True


# - Exception testing -


def test_duplicate_insert_raises(db):
    db.execute("INSERT INTO skills (name) VALUES ('pytest')")
    db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO skills (name) VALUES ('pytest')")  # duplicate


def test_rollback_on_error(db):
    """Transaction rolls back cleanly on failure."""
    try:
        db.execute("BEGIN")
        db.execute("INSERT INTO skills (name) VALUES ('new-skill')")
        db.execute("INSERT INTO skills (name) VALUES ('new-skill')")  # dup
    except sqlite3.IntegrityError:
        db.execute("ROLLBACK")
    count = db.execute("SELECT COUNT(*) FROM skills WHERE name='new-skill'").fetchone()
    assert count[0] == 0  # rolled back


# - Monkeypatch -


def test_monkeypatch_env(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    import os

    assert os.getenv("LOG_LEVEL") == "DEBUG"
