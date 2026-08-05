"""Bootstrap coverage (Task 9): build_services with embedder/store mocked so no
model is downloaded at test time (hermetic, AC#6)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from skill_vault.bootstrap import Services, build_services
from skill_vault.config import Settings


def _settings(db_path: str) -> Settings:
    return Settings(
        db_path=db_path,
        vector_backend="sqlite_vec",
        embed_model="fake-model",
        trust_allow="verified,user",
        curator_key=None,
        mcp_host="0.0.0.0",
        mcp_port=8000,
        web_host="0.0.0.0",
        web_port=8080,
        seed_dir="./seed",
        pgvector_dsn=None,
        rate_limit_per_minute=60,
        admin_username="admin",
        admin_password="pw",
    )


def test_build_services_constructs_stack(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("skill_vault.bootstrap.Embedder", lambda model: MagicMock())
    monkeypatch.setattr("skill_vault.bootstrap.build_store", lambda *a, **k: MagicMock())

    services = build_services(_settings(str(tmp_path / "app.db")))

    assert isinstance(services, Services)
    assert services.auth is not None
    assert services.search is not None
    assert services.trust is not None
    assert services.registry is not None
    # migrations ran against the temp DB
    tables = {
        r["name"]
        for r in services.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "skills" in tables and "agents" in tables
