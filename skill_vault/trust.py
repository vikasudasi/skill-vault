"""Trust layer & skill supply-chain security (Task 5, headline differentiator).

What it provides
----------------
- **Content addressing** — every skill version is pinned by ``sha256`` of its
  *canonical* serialization; the read path recomputes the hash and refuses to
  return content that doesn't match (integrity is non-optional).
- **Trust tiers** — ``verified`` (signed by a known curator key) | ``user``
  (own/private skill) | ``public`` (community). Surfaced on search + get.
- **ed25519 signatures** — a curator can sign a skill payload; consumers can
  verify provenance (``verify_skill``).
- **Trust policy** — a host may restrict which tiers its servers will return
  (e.g. ``allow_tiers: [verified, user]``); disallowed skills are refused.

Canonical serialization (section 5)
-----------------------------------
Payload is JSON with sorted keys at every level, compact separators, and
unescaped UTF-8, so the same skill bytes hash identically on any host/run.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterable
from typing import Any

from skill_vault.errors import ForbiddenError, IntegrityError

TIER_VERIFIED = "verified"
TIER_USER = "user"
TIER_PUBLIC = "public"
ALL_TIERS = (TIER_VERIFIED, TIER_USER, TIER_PUBLIC)
DEFAULT_ALLOW_TIERS = (TIER_VERIFIED, TIER_USER)

ed25519 = None  # lazy-imported
InvalidSignature = None  # lazy-imported


def _ed25519() -> tuple[Any, Any]:
    global ed25519, InvalidSignature
    if ed25519 is None:
        from cryptography.exceptions import InvalidSignature as _IS
        from cryptography.hazmat.primitives.asymmetric import ed25519 as _ed

        InvalidSignature = _IS
        ed25519 = _ed
    return ed25519, InvalidSignature


# -- canonical serialization --------------------------------------------------


def canonical_payload(
    *,
    name: str,
    description: str,
    tags: Iterable[str],
    triggers: Iterable[str],
    meta_json: dict[str, Any],
    body: str,
) -> bytes:
    """Deterministic serialization of a skill's content, suitable for hashing/signing."""
    payload = {
        "name": name,
        "description": description,
        "tags": sorted(tags),
        "triggers": sorted(triggers),
        "meta": meta_json,
        "body": body,
    }
    return canonical_json(payload).encode("utf-8")


def canonical_json(obj: Any) -> str:
    """JSON with sorted keys at every depth, compact separators, UTF-8 preserved."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(payload: bytes) -> str:
    """sha256 (hex) of a canonical skill payload — the content address."""
    return hashlib.sha256(payload).hexdigest()


# -- ed25519 signatures -------------------------------------------------------


def generate_curator_keypair() -> tuple[str, str]:
    """:return: ``(private_key_b64, public_key_b64)`` — private is the signing secret."""
    ed, _ = _ed25519()
    key = ed.Ed25519PrivateKey.generate()
    priv = key.private_bytes_raw()
    pub = key.public_key().public_bytes_raw()
    return _b64(priv), _b64(pub)


def sign(payload: bytes, private_key_b64: str) -> str:
    """Sign a canonical payload with the curator's private key (base64 sig)."""
    ed, _ = _ed25519()
    sk = ed.Ed25519PrivateKey.from_private_bytes(_unb64(private_key_b64))
    return _b64(sk.sign(payload))


def verify(payload: bytes, signature_b64: str, public_key_b64: str) -> bool:
    """Verify a detached signature; returns False (never raises) on mismatch."""
    from cryptography.exceptions import InvalidSignature as _InvalidSignature

    ed, _ = _ed25519()
    try:
        pk = ed.Ed25519PublicKey.from_public_bytes(_unb64(public_key_b64))
        pk.verify(_unb64(signature_b64), payload)
        return True
    except (ValueError, TypeError, _InvalidSignature):
        return False


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


# -- policy + service ---------------------------------------------------------


class TrustPolicy:
    """Which tiers this host will serve to agents."""

    def __init__(self, allow_tiers: Iterable[str], known_public_keys: Iterable[str] = ()) -> None:
        self.allow_tiers = set(allow_tiers)
        self.known_public_keys = set(known_public_keys)

    def allows(self, tier: str) -> bool:
        return tier in self.allow_tiers


class TrustService:
    """Content-integrity, tier resolution, signature verification, and policy hooks."""

    def __init__(
        self,
        db: sqlite3.Connection,
        *,
        allow_tiers: Iterable[str] = DEFAULT_ALLOW_TIERS,
        known_public_keys: Iterable[str] = (),
    ) -> None:
        self._db = db
        self._policy = TrustPolicy(allow_tiers, known_public_keys)

    # -- tier ---------------------------------------------------------------

    def compute_tier(
        self, *, owner_agent_id: str | None, signature: str | None, public_key: str | None
    ) -> str:
        """Tier for a newly published skill.

        - A valid signature by a known curator public key => ``verified``.
        - Otherwise an owned/private skill => ``user``.
        - Otherwise a public/community skill => ``public``.
        """
        if signature and public_key and public_key in self._policy.known_public_keys:
            return TIER_VERIFIED
        if owner_agent_id is not None:
            return TIER_USER
        return TIER_PUBLIC

    def record(
        self,
        version_id: str,
        tier: str,
        *,
        signature: str | None = None,
        public_key: str | None = None,
        signed_by: str | None = None,
    ) -> None:
        """Upsert the trust record for a skill version (idempotent)."""
        now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._db.execute("DELETE FROM trust WHERE skill_version_id = ?", (version_id,))
        self._db.execute(
            "INSERT INTO trust(id, skill_version_id, tier, signed_by, signature, public_key, "
            "verified_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), version_id, tier, signed_by, signature, public_key, now),
        )
        self._db.commit()

    def resolve_tier(self, version_id: str) -> str:
        """Stored tier, falling back to derivation (own->user, else public)."""
        row = self._db.execute(
            "SELECT tier FROM trust WHERE skill_version_id = ?", (version_id,)
        ).fetchone()
        if row is not None:
            return str(row["tier"])
        owner = self._db.execute(
            "SELECT s.owner_agent_id FROM skill_versions v JOIN skills s ON s.id = v.skill_id "
            "WHERE v.id = ?",
            (version_id,),
        ).fetchone()
        if owner is not None and owner["owner_agent_id"] is not None:
            return TIER_USER
        return TIER_PUBLIC

    # -- policy -------------------------------------------------------------

    def policy_allows(self, version_id: str) -> bool:
        return self._policy.allows(self.resolve_tier(version_id))

    def ensure_allowed(self, version_id: str) -> None:
        """Raise :class:`ForbiddenError` if the host policy forbids this skill's tier."""
        if not self.policy_allows(version_id):
            raise ForbiddenError(
                f"skill {version_id} has tier '{self.resolve_tier(version_id)}', which the host "
                "trust policy does not allow"
            )

    # -- integrity ----------------------------------------------------------

    def verify_integrity(self, version_id: str, payload: bytes) -> dict[str, Any]:
        """Recompute the content address and compare with the stored pin."""
        row = self._db.execute(
            "SELECT content_hash FROM skill_versions WHERE id = ?", (version_id,)
        ).fetchone()
        if row is None:
            raise IntegrityError("unknown skill version")
        actual = content_hash(payload)
        expected = row["content_hash"]
        return {"expected": expected, "actual": actual, "ok": expected == actual}

    def ensure_integrity(self, version_id: str, payload: bytes) -> None:
        """Non-optional integrity check — raises on mismatch (tampering)."""
        result = self.verify_integrity(version_id, payload)
        if not result["ok"]:
            raise IntegrityError(
                f"content hash mismatch for {version_id}: stored {result['expected']} != "
                f"actual {result['actual']}"
            )

    # -- signature ----------------------------------------------------------

    def verify_signature(self, version_id: str, payload: bytes) -> dict[str, Any]:
        """Check the detached signature (if any) against the stored public key."""
        row = self._db.execute(
            "SELECT tier, signature, public_key, signed_by, verified_at FROM trust "
            "WHERE skill_version_id = ?",
            (version_id,),
        ).fetchone()
        if row is None or not row["signature"] or not row["public_key"]:
            return {"signed": False, "verified": False, "tier": self.resolve_tier(version_id)}
        ok = verify(payload, row["signature"], row["public_key"])
        return {
            "signed": True,
            "verified": ok,
            "tier": row["tier"],
            "signed_by": row["signed_by"],
            "verified_at": row["verified_at"],
        }
