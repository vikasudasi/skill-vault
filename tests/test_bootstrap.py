"""Bootstrap coverage (Task 9): build_services with embedder/store mocked so no
model is downloaded at test time (hermetic, AC#6)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

from skill_vault.bootstrap import Services, build_services
from skill_vault.config import Settings
from skill_vault.models import SkillInput
from skill_vault.service import _build_payload
from skill_vault.trust import (
    TIER_VERIFIED,
    generate_curator_keypair,
    public_key_from_private_key,
    sign,
)


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


def test_build_services_wires_curator_public_key_verified_resolution(
    monkeypatch, tmp_path: Path
) -> None:
    """A skill signed by the configured curator key resolves to 'verified' end-to-end."""
    monkeypatch.setattr("skill_vault.bootstrap.Embedder", lambda model: MagicMock())
    monkeypatch.setattr("skill_vault.bootstrap.build_store", lambda *a, **k: MagicMock())

    priv, pub = generate_curator_keypair()
    settings = replace(_settings(str(tmp_path / "app.db")), curator_key=priv)
    services = build_services(settings)

    # the trust policy knows the public key derived from the configured private key
    assert services.trust._policy.known_public_keys == {pub}

    skill = SkillInput(
        name="signed-skill",
        description="desc",
        tags=["a"],
        triggers=["b"],
        body="body text",
        meta={},
    )
    signature = sign(_build_payload(skill), priv)
    services.registry.admin_publish_seed(
        skill,
        signature=signature,
        public_key=public_key_from_private_key(priv),
        signed_by="Skill Vault curated library",
    )

    row = services.db.execute(
        "SELECT v.id AS vid FROM skills s JOIN skill_versions v "
        "ON v.id = s.current_version_id WHERE s.name = 'signed-skill'"
    ).fetchone()
    assert services.trust.resolve_tier(row["vid"]) == TIER_VERIFIED
