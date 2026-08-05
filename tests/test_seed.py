"""Seed command tests (Task 10) — hermetic, no model download.

Covers the seed parser contract, idempotent ingestion into the registry, and
verified-tier resolution for a curator-signed seed skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import FakeEmbedder, FakeStore

from skill_vault.auth import AuthService
from skill_vault.bootstrap import Services
from skill_vault.db import connect, run_migrations
from skill_vault.search import SearchService
from skill_vault.seed import discover_seed_dir, parse_skill_file, seed_skills
from skill_vault.service import RegistryService
from skill_vault.trust import TIER_PUBLIC, TIER_VERIFIED, TrustService, generate_curator_keypair

MIGRATIONS = Path(__file__).parent.parent / "migrations"
SEED_SKILLS = Path(__file__).parent.parent / "skill_vault" / "data" / "skills"


def _services(tmp_path: Path, known_public_keys: list[str] | None = None):
    db = connect(str(tmp_path / "app.db"))
    run_migrations(db, str(MIGRATIONS))
    auth = AuthService(db, rate_limit=100000)
    search = SearchService(db, FakeStore(), FakeEmbedder())
    trust = TrustService(
        db,
        allow_tiers=(TIER_VERIFIED, "user", TIER_PUBLIC),
        known_public_keys=known_public_keys or [],
    )
    registry = RegistryService(db, auth=auth, search=search, trust=trust)
    return Services(db=db, auth=auth, search=search, trust=trust, registry=registry)


# -- parse ---------------------------------------------------------------


def test_parse_skill_file_parses_frontmatter():
    path = SEED_SKILLS / "git-workflow" / "SKILL.md"
    seed = parse_skill_file(path)
    assert seed.skill.name == "git-workflow"
    assert seed.skill.description
    assert seed.skill.tags
    assert seed.skill.triggers
    assert seed.skill.body.startswith("# Safe Git Branch Workflow")
    assert seed.skill.meta["source"] == "Skill Vault curated library"
    assert seed.skill.meta["complexity"] == "low"
    assert seed.verify is False


def test_parse_signed_skill_has_verify_flag():
    path = SEED_SKILLS / "python-cli-typer" / "SKILL.md"
    seed = parse_skill_file(path)
    assert seed.verify is True


def test_parse_requires_name(tmp_path):
    bad = tmp_path / "SKILL.md"
    bad.write_text("---\ndescription: no name here\n---\n# body\n")
    with pytest.raises(ValueError):
        parse_skill_file(bad)


def test_parse_requires_body(tmp_path):
    bad = tmp_path / "SKILL.md"
    bad.write_text("---\nname: x\ndescription: d\n---\n")
    with pytest.raises(ValueError):
        parse_skill_file(bad)


def test_parse_rejects_missing_frontmatter(tmp_path):
    bad = tmp_path / "SKILL.md"
    bad.write_text("# just a body, no frontmatter\n")
    with pytest.raises(ValueError):
        parse_skill_file(bad)


# -- discovery -----------------------------------------------------------


def test_discover_seed_dir_resolves_package_dir():
    # the default `./skill_vault/data/skills` should resolve regardless of CWD
    resolved = discover_seed_dir("./skill_vault/data/skills")
    assert resolved.is_dir()
    assert resolved.name == "skills"


def test_discover_seed_dir_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        discover_seed_dir(tmp_path / "nope")


# -- seed_skills ---------------------------------------------------------


def test_seed_ingests_all_and_is_idempotent(tmp_path):
    services = _services(tmp_path)
    first = seed_skills(services, SEED_SKILLS, curator_key=None)
    for d in sorted(p for p in SEED_SKILLS.iterdir() if p.is_dir()):
        n = services.db.execute("SELECT COUNT(*) FROM skills WHERE name=?", (d.name,)).fetchone()[0]
        assert n == 1, f"{d.name} not seeded"
    second = seed_skills(services, SEED_SKILLS, curator_key=None)
    assert first >= 15, first  # AC#1: >=15 curated skills
    assert second == 0  # idempotent: nothing re-seeded
    total = services.db.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
    assert total == first


def test_seed_signs_verified_skill_with_curator_key(tmp_path):
    priv, pub = generate_curator_keypair()
    services = _services(tmp_path, known_public_keys=[pub])
    seed_skills(services, SEED_SKILLS, curator_key=priv)

    # the signed skill resolves to verified
    row = services.db.execute(
        "SELECT s.id, v.id AS vid FROM skills s "
        "JOIN skill_versions v ON v.id=s.current_version_id "
        "WHERE s.name='python-cli-typer'"
    ).fetchone()
    assert services.trust.resolve_tier(row["vid"]) == TIER_VERIFIED

    # signature genuinely verifies
    detail = services.registry.get(row["id"])
    assert detail.trust == TIER_VERIFIED
    assert detail.verified is True

    # normal skills stay public
    g = services.db.execute(
        "SELECT v.id AS vid FROM skills s JOIN skill_versions v ON v.id=s.current_version_id "
        "WHERE s.name='git-workflow'"
    ).fetchone()
    assert services.trust.resolve_tier(g["vid"]) == TIER_PUBLIC


def test_seed_verify_flag_without_curator_key_stays_unverified(tmp_path):
    services = _services(tmp_path)
    seed_skills(services, SEED_SKILLS, curator_key=None)
    g = services.db.execute(
        "SELECT v.id AS vid FROM skills s JOIN skill_versions v ON v.id=s.current_version_id "
        "WHERE s.name='python-cli-typer'"
    ).fetchone()
    assert services.trust.resolve_tier(g["vid"]) == TIER_PUBLIC


def test_seed_search_returns_ranged_results(tmp_path):
    services = _services(tmp_path)
    seed_skills(services, SEED_SKILLS, curator_key=None)
    # FakeStore returns all in insertion order; just confirm cards are produced
    cards = services.registry.search("docker compose", scope="global", limit=20)
    assert len(cards) >= 15
    names = {c.name for c in cards}
    assert "docker-compose-services" in names
