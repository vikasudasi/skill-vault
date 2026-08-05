"""Reusable fixture helpers for the Skill Vault test suite (Task 9, AC#2).

Provides:
- :func:`load_skill_md` — read a sample SKILL.md from ``tests/fixtures/skills``.
- :func:`load_signed_skill` — the genuinely-signed curated skill fixture.
- :func:`build_preseeded_services` — a full Services object seeded from the
  docker-ce sample skill + a signed skill, against a hermetic temp SQLite DB +
  in-memory/on-disk vector store + fake embedder (no model download).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from conftest import FakeEmbedder

from skill_vault.auth import AuthService
from skill_vault.bootstrap import Services
from skill_vault.db import connect, run_migrations
from skill_vault.models import SkillInput
from skill_vault.search import SearchService, SqliteVecStore
from skill_vault.service import RegistryService
from skill_vault.trust import TrustService

FIXTURES = Path(__file__).parent
SKILLS = FIXTURES / "skills"
SIGNED = FIXTURES / "signed"
MIGRATIONS = Path(__file__).parent.parent.parent / "migrations"


def load_skill_md(name: str) -> str:
    """Return raw SKILL.md text for a sample skill (no frontmatter parsing here)."""
    path = SKILLS / name / "SKILL.md"
    if not path.exists():
        raise FileNotFoundError(f"no sample skill fixture at {path}")
    return path.read_text()


def sample_skill(name: str = "docker-ce") -> SkillInput:
    """A :class:`SkillInput` parsed from a sample SKILL.md (ignores YAML frontmatter)."""
    text = load_skill_md(name)
    body = text.split("---", 2)[-1].strip()  # drop YAML frontmatter block
    return SkillInput(
        name=name,
        description=f"{name} operational runbook",
        tags=["devops"],
        triggers=["docker"],
        body=body,
        meta={},
    )


def load_signed_skill() -> dict:
    """Load the genuinely-signed curated skill fixture."""
    data = json.loads((SIGNED / "fixture.json").read_text())
    return data


def build_preseeded_services(tmp_path: Path, signed: bool = True) -> Services:
    """Hermetic Services preseeded with the sample skill (and optionally the signed one)."""
    db = connect(str(tmp_path / "app.db"))
    run_migrations(db, str(MIGRATIONS))
    auth = AuthService(db, rate_limit=100000)
    store = SqliteVecStore(str(tmp_path / "vec.db"))
    search = SearchService(db, store, FakeEmbedder())

    signed_fixture = load_signed_skill() if signed else None
    known_keys: list[str] = []
    if signed_fixture:
        known_keys.append(signed_fixture["public_key_b64"])
    trust = TrustService(
        db, allow_tiers=("verified", "user", "public"), known_public_keys=known_keys
    )
    registry = RegistryService(db, auth=auth, search=search, trust=trust)

    # seed the sample skill under an agent
    owner = auth.create_agent("seed-owner")
    registry.admin_publish(owner, sample_skill(), "global")

    if signed_fixture:
        # seed the signed skill via admin so we can record it as verified
        registry.admin_publish(
            owner,
            SkillInput(
                name=signed_fixture["name"],
                description=signed_fixture["description"],
                tags=signed_fixture["tags"],
                triggers=signed_fixture["triggers"],
                body=signed_fixture["body"],
                meta=signed_fixture["meta"],
            ),
            "global",
        )

    return Services(db=db, auth=auth, search=search, trust=trust, registry=registry)


def verify_signed_payload(signed_fixture: dict) -> dict:
    """Verify the curated skill's detached signature via the trust layer primitives."""
    from skill_vault.trust import verify

    payload = base64.b64decode(signed_fixture["payload_b64"])
    ok = verify(payload, signed_fixture["signature_b64"], signed_fixture["public_key_b64"])
    return {"ok": ok, "payload": payload}
