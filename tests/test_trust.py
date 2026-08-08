"""Unit tests for the trust layer & supply-chain security (Task 5)."""

from __future__ import annotations

import pytest

from skill_vault.errors import ForbiddenError, IntegrityError
from skill_vault.trust import (
    TIER_PUBLIC,
    TIER_USER,
    TIER_VERIFIED,
    TrustService,
    canonical_payload,
    content_hash,
    generate_curator_keypair,
    public_key_from_private_key,
    sign,
    verify,
)


def test_canonical_payload_is_deterministic():
    p1 = canonical_payload(
        name="docker",
        description="manage containers",
        tags=["cli", "devops"],
        triggers=["docker"],
        meta_json={"license": "MIT"},
        body="...commands...",
    )
    p2 = canonical_payload(
        name="docker",
        description="manage containers",
        tags=["devops", "cli"],
        triggers=["docker"],
        meta_json={"license": "MIT"},
        body="...commands...",
    )
    assert p1 == p2
    assert content_hash(p1) == content_hash(p2)


def test_canonical_payload_changes_with_content():
    p1 = canonical_payload(name="a", description="x", tags=[], triggers=[], meta_json={}, body="b1")
    p2 = canonical_payload(name="a", description="x", tags=[], triggers=[], meta_json={}, body="b2")
    assert content_hash(p1) != content_hash(p2)


def test_sign_verify_roundtrip():
    priv, pub = generate_curator_keypair()
    payload = b"canonical skill bytes"
    sig = sign(payload, priv)
    assert verify(payload, sig, pub) is True


def test_verify_rejects_tampered_payload():
    priv, pub = generate_curator_keypair()
    payload = b"original"
    sig = sign(payload, priv)
    assert verify(b"tampered", sig, pub) is False


def test_verify_rejects_wrong_key():
    priv, _ = generate_curator_keypair()
    _, other_pub = generate_curator_keypair()
    sig = sign(b"payload", priv)
    assert verify(b"payload", sig, other_pub) is False


def test_public_key_derived_from_private_key():
    priv, pub = generate_curator_keypair()
    assert public_key_from_private_key(priv) == pub


def test_compute_tier_verified_with_derived_key():
    priv, pub = generate_curator_keypair()
    svc = TrustService(None, known_public_keys=[public_key_from_private_key(priv)])
    assert svc.compute_tier(owner_agent_id=None, signature="s", public_key=pub) == TIER_VERIFIED


def test_compute_tier_signed_known_key_is_verified():
    _, pub = generate_curator_keypair()
    svc = TrustService(None, known_public_keys=[pub])
    assert svc.compute_tier(owner_agent_id=None, signature="sig", public_key=pub) == TIER_VERIFIED


def test_compute_tier_owned_is_user():
    svc = TrustService(None)
    assert svc.compute_tier(owner_agent_id="agent-1", signature=None, public_key=None) == TIER_USER


def test_compute_tier_otherwise_public():
    svc = TrustService(None)
    assert svc.compute_tier(owner_agent_id=None, signature=None, public_key=None) == TIER_PUBLIC


def test_resolve_tier_falls_back_to_user_for_owned(db):
    owner = _insert_owner(db, name="docker")
    _insert_version(db, owner)
    vid = str(db.execute("SELECT id FROM skill_versions LIMIT 1").fetchone()["id"])
    svc = TrustService(db)
    assert svc.resolve_tier(vid) == TIER_USER


def test_resolve_tier_falls_back_to_public_for_global(db):
    _insert_version(db, None, name="docker")
    vid = str(db.execute("SELECT id FROM skill_versions LIMIT 1").fetchone()["id"])
    svc = TrustService(db)
    assert svc.resolve_tier(vid) == TIER_PUBLIC


def test_policy_allows_and_enforces(db):
    _insert_version(db, None, name="docker")
    vid = str(db.execute("SELECT id FROM skill_versions LIMIT 1").fetchone()["id"])
    strict = TrustService(db, allow_tiers=[TIER_VERIFIED, TIER_USER])
    assert strict.policy_allows(vid) is False
    with pytest.raises(ForbiddenError):
        strict.ensure_allowed(vid)
    lax = TrustService(db, allow_tiers=[TIER_VERIFIED, TIER_USER, TIER_PUBLIC])
    assert lax.policy_allows(vid) is True


def test_verify_integrity_mismatch(db):
    row = _insert_version(db, None, name="docker")
    svc = TrustService(db)
    bad = svc.verify_integrity(row["id"], b"different bytes")
    assert bad["ok"] is False
    with pytest.raises(IntegrityError):
        svc.ensure_integrity(row["id"], b"different bytes")


def test_verify_signature_signed(db):
    priv, pub = generate_curator_keypair()
    row = _insert_version(db, None, name="docker")
    payload = _payload_for(row)
    sig = sign(payload, priv)
    svc = TrustService(db, known_public_keys=[pub])
    svc.record(row["id"], TIER_VERIFIED, signature=sig, public_key=pub, signed_by="curator-1")
    res = svc.verify_signature(row["id"], payload)
    assert res["signed"] is True
    assert res["verified"] is True
    assert res["signed_by"] == "curator-1"


def test_verify_signature_unsigned(db):
    row = _insert_version(db, None, name="docker")
    svc = TrustService(db)
    res = svc.verify_signature(row["id"], _payload_for(row))
    assert res["signed"] is False
    assert res["verified"] is False


# -- helpers ----------------------------------------------------------------


def _insert_owner(db, name: str = "agent") -> str:
    import uuid

    aid = str(uuid.uuid4())
    db.execute("INSERT INTO agents(id, name) VALUES (?, ?)", (aid, name))
    db.commit()
    return aid


def _insert_version(db, owner_agent_id, name: str = "docker"):
    import json
    import uuid

    sid, vid = str(uuid.uuid4()), str(uuid.uuid4())
    meta = {"license": "MIT"}
    payload = canonical_payload(
        name=name,
        description="manage containers",
        tags=["devops"],
        triggers=["docker"],
        meta_json=meta,
        body="...commands...",
    )
    db.execute(
        "INSERT INTO skills(id, name, owner_agent_id, visibility) VALUES (?, ?, ?, ?)",
        (sid, name, owner_agent_id, "global" if owner_agent_id is None else "personal"),
    )
    db.execute(
        "INSERT INTO skill_versions(id, skill_id, version, content_hash, name, description, "
        "tags, triggers, meta_json, body) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            vid,
            sid,
            1,
            content_hash(payload),
            name,
            "manage containers",
            json.dumps(["devops"]),
            json.dumps(["docker"]),
            json.dumps(meta),
            "...commands...",
        ),
    )
    db.commit()
    return {"id": vid, "skill_id": sid, "payload": payload}


def _payload_for(row) -> bytes:
    return row["payload"]
