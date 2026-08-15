"""Tests for skill version file attachments (scripts/references)."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import FakeEmbedder

from skill_vault.auth import AuthService
from skill_vault.db import connect, run_migrations
from skill_vault.errors import NotFoundError
from skill_vault.models import SkillInput
from skill_vault.search import SearchService, SqliteVecStore
from skill_vault.service import RegistryService
from skill_vault.trust import (
    TIER_VERIFIED,
    TrustService,
    canonical_payload,
    content_hash,
    generate_curator_keypair,
)

MIGRATIONS = str(Path(__file__).resolve().parent.parent / "migrations")


def _services(tmp_path, curator_key=None):
    db = connect(str(tmp_path / "app.db"))
    run_migrations(db, MIGRATIONS)
    auth = AuthService(db, rate_limit=100000)
    store = SqliteVecStore(str(tmp_path / "vec.db"))
    search = SearchService(db, store, FakeEmbedder())
    trust = TrustService(db, allow_tiers=("verified", "user", "public"))
    reg = RegistryService(db, auth=auth, search=search, trust=trust, curator_key=curator_key)
    return db, auth, reg


def _skill(name="docker", body="# docker\nmanage containers"):
    return SkillInput(
        name=name,
        description=f"{name} skill description",
        tags=["devops", "cli"],
        triggers=["deploy", "build"],
        body=body,
        meta={},
    )


def _version_id(db, skill_id: str) -> str:
    return db.execute("SELECT current_version_id FROM skills WHERE id = ?", (skill_id,)).fetchone()[
        "current_version_id"
    ]


def test_migration_005_creates_skill_version_files_table(db):
    tables = {
        row["name"]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "skill_version_files" in tables
    cols = {row["name"] for row in db.execute("PRAGMA table_info(skill_version_files)").fetchall()}
    assert {
        "id",
        "skill_version_id",
        "kind",
        "filename",
        "content",
        "content_hash",
        "created_at",
    } <= cols


def test_file_crud_lifecycle(tmp_path):
    db, auth, reg = _services(tmp_path)
    onboard = auth.onboard("agent-a")
    res = reg.publish(skill=_skill(), visibility="personal", agent_key=onboard.raw_key)
    vid = _version_id(db, res.id)

    sf = reg.add_skill_file(vid, "script", "run.sh", "#!/bin/bash\necho hi")
    assert sf.kind == "script"
    assert sf.filename == "run.sh"
    assert sf.content == "#!/bin/bash\necho hi"
    assert len(sf.content_hash) == 64

    listed = reg.list_skill_files(vid)
    assert len(listed) == 1
    assert listed[0].id == sf.id
    assert listed[0].filename == "run.sh"
    assert not hasattr(listed[0], "content")

    fetched = reg.get_skill_file(sf.id)
    assert fetched.content == "#!/bin/bash\necho hi"

    reg.delete_skill_file(sf.id)
    assert reg.list_skill_files(vid) == []
    with pytest.raises(NotFoundError):
        reg.get_skill_file(sf.id)


def test_hash_backward_compat_no_files(tmp_path):
    _, auth, reg = _services(tmp_path)
    onboard = auth.onboard("agent-a")
    skill = _skill()
    res = reg.publish(skill=skill, visibility="personal", agent_key=onboard.raw_key)

    expected_payload = canonical_payload(
        name=skill.name,
        description=skill.description,
        tags=skill.tags,
        triggers=skill.triggers,
        meta_json=skill.meta,
        body=skill.body,
    )
    assert res.content_hash == content_hash(expected_payload)

    # Explicit empty files list must produce identical hash.
    with_files_none = canonical_payload(
        name=skill.name,
        description=skill.description,
        tags=skill.tags,
        triggers=skill.triggers,
        meta_json=skill.meta,
        body=skill.body,
        files=None,
    )
    assert content_hash(with_files_none) == res.content_hash


def test_hash_changes_when_files_added(tmp_path):
    db, auth, reg = _services(tmp_path)
    onboard = auth.onboard("agent-a")
    res = reg.publish(skill=_skill(), visibility="personal", agent_key=onboard.raw_key)
    vid = _version_id(db, res.id)
    original_hash = res.content_hash

    reg.add_skill_file(vid, "reference", "notes.md", "extra context")
    row = db.execute("SELECT content_hash FROM skill_versions WHERE id = ?", (vid,)).fetchone()
    assert row["content_hash"] != original_hash

    files = reg._list_skill_files_raw(vid)
    version_row = reg._load_version_row(vid)
    payload = canonical_payload(
        name=version_row["name"],
        description=version_row["description"],
        tags=["devops", "cli"],
        triggers=["deploy", "build"],
        meta_json={},
        body=version_row["body"],
        files=files,
    )
    assert row["content_hash"] == content_hash(payload)


def test_get_skill_includes_file_metadata(tmp_path):
    db, auth, reg = _services(tmp_path)
    onboard = auth.onboard("agent-a")
    res = reg.publish(skill=_skill(), visibility="personal", agent_key=onboard.raw_key)
    vid = _version_id(db, res.id)

    reg.add_skill_file(vid, "script", "deploy.sh", "echo deploy")
    reg.add_skill_file(vid, "reference", "README.md", "# docs")

    detail = reg.get(identifier=res.id, agent_key=onboard.raw_key)
    assert detail.files is not None
    assert len(detail.files) == 2
    names = {f.filename for f in detail.files}
    assert names == {"deploy.sh", "README.md"}
    for f in detail.files:
        assert f.kind in ("script", "reference")
        assert len(f.content_hash) == 64
        assert f.created_at


def test_cascade_delete_removes_files(tmp_path):
    db, auth, reg = _services(tmp_path)
    onboard = auth.onboard("agent-a")
    res = reg.publish(skill=_skill(), visibility="personal", agent_key=onboard.raw_key)
    vid = _version_id(db, res.id)
    sf = reg.add_skill_file(vid, "script", "tool.py", "print('ok')")

    reg.delete(identifier=res.id, agent_key=onboard.raw_key)
    count = db.execute(
        "SELECT COUNT(*) AS c FROM skill_version_files WHERE id = ?", (sf.id,)
    ).fetchone()["c"]
    assert count == 0


def test_add_skill_file_resigns_verified_version(tmp_path):
    """Adding a file to a curator-signed (verified) skill must re-sign the
    file-inclusive payload so the detached signature stays valid."""
    priv, _pub = generate_curator_keypair()
    db, auth, reg = _services(tmp_path, curator_key=priv)
    onboard = auth.onboard("agent-a")
    res = reg.admin_publish(onboard.agent_id, _skill(), visibility="global")
    vid = _version_id(db, res.id)

    # Pre-condition: global admin publish is auto-signed verified.
    assert reg.get(identifier=res.id).verified is True
    assert reg.get(identifier=res.id).trust == TIER_VERIFIED

    reg.add_skill_file(vid, "script", "deploy.sh", "echo deploy")

    detail = reg.get(identifier=res.id)
    # Signature is still valid over the new file-inclusive payload.
    assert detail.verified is True
    assert detail.trust == TIER_VERIFIED


def test_delete_skill_file_resigns_verified_version(tmp_path):
    """Removing a file from a verified skill re-signs the reduced payload."""
    priv, _pub = generate_curator_keypair()
    db, auth, reg = _services(tmp_path, curator_key=priv)
    onboard = auth.onboard("agent-a")
    res = reg.admin_publish(onboard.agent_id, _skill(), visibility="global")
    vid = _version_id(db, res.id)
    sf = reg.add_skill_file(vid, "reference", "notes.md", "extra context")
    assert reg.get(identifier=res.id).verified is True

    reg.delete_skill_file(sf.id)

    detail = reg.get(identifier=res.id)
    assert detail.verified is True
    assert detail.trust == TIER_VERIFIED
    assert detail.files == []
