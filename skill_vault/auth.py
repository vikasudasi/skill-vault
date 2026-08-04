"""Per-agent identity, API-key lifecycle, and request auth resolution.

Security notes
--------------
- Raw keys are high-entropy (32 bytes CSPRNG), prefixed ``sv_``, shown to the
  user **exactly once** at issuance and never stored.
- The DB stores only ``key_hash`` = sha256(hex) of the raw key; a leaked DB
  cannot reveal working keys.
- Rate limiting is a per-key fixed window enforced by :class:`FixedWindowLimiter`
  with an injectable clock (so tests are deterministic).
- ``resolve()`` distinguishes *no key* (guest → global-only) from *presented but
  invalid/revoked* (→ 401/403), so a bad credential can never silently downgrade
  to guest access.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time as _time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from skill_vault.errors import (
    AuthenticationError,
    RateLimitError,
    RevokedKeyError,
)

KEY_PREFIX_LEADER = "sv_"


def generate_raw_key() -> str:
    """Return a new high-entropy API key like ``sv_<43 url-safe chars>``."""
    return f"{KEY_PREFIX_LEADER}{secrets.token_urlsafe(32)}"


def hash_key(raw_key: str) -> str:
    """One-way hash of a raw key, as stored at rest."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def key_prefix(raw_key: str) -> str:
    """Short display prefix (first 8 chars past the leader) for the UI."""
    return raw_key[: len(KEY_PREFIX_LEADER) + 8]


@dataclass(frozen=True, slots=True)
class AgentContext:
    """Resolved identity for one request. ``scope`` is ``guest`` or ``authenticated``."""

    agent_id: str | None
    key_id: str | None
    scope: str = "guest"

    @property
    def is_authenticated(self) -> bool:
        return self.scope == "authenticated"


@dataclass(frozen=True, slots=True)
class OnboardResult:
    agent_id: str
    key_id: str
    raw_key: str  # shown once
    key_prefix: str


@dataclass(frozen=True, slots=True)
class IssuedKey:
    key_id: str
    raw_key: str
    key_prefix: str


@dataclass(frozen=True, slots=True)
class KeyInfo:
    key_id: str
    key_prefix: str
    created_at: str
    last_used_at: str | None
    revoked_at: str | None


class FixedWindowLimiter:
    """Per-key fixed-window counter with an injectable clock for determinism."""

    def __init__(
        self, limit: int, window_secs: int, *, time_fn: Callable[[], float] = _time.monotonic
    ) -> None:
        if limit <= 0:
            raise ValueError("rate limit must be positive")
        self.limit = limit
        self.window_secs = window_secs
        self._now = time_fn
        self._windows: dict[str, tuple[float, int]] = {}  # key -> (window_start, count)

    def allow(self, key_id: str) -> bool:
        now = self._now()
        window_start, count = self._windows.get(key_id, (0, 0))
        if now - window_start >= self.window_secs:
            window_start, count = now, 0
        if count >= self.limit:
            self._windows[key_id] = (window_start, count)
            return False
        self._windows[key_id] = (window_start, count + 1)
        return True


class AuthService:
    """Agent/key CRUD plus request credential resolution against one SQLite DB."""

    def __init__(
        self,
        db: sqlite3.Connection,
        *,
        rate_limit: int = 60,
        rate_window_secs: int = 60,
        time_fn: Callable[[], float] = _time.monotonic,
    ) -> None:
        self._db = db
        self._limiter = FixedWindowLimiter(rate_limit, rate_window_secs, time_fn=time_fn)

    # -- onboarding ----------------------------------------------------------

    def onboard(self, name: str) -> OnboardResult:
        """Create an agent and issue its first key (shown once)."""
        agent_id = self.create_agent(name)
        issued = self.issue_key(agent_id)
        return OnboardResult(
            agent_id=agent_id,
            key_id=issued.key_id,
            raw_key=issued.raw_key,
            key_prefix=issued.key_prefix,
        )

    def create_agent(self, name: str) -> str:
        if not name or not name.strip():
            raise AuthenticationError("agent name must not be empty")
        agent_id = str(uuid.uuid4())
        self._db.execute("INSERT INTO agents(id, name) VALUES (?, ?)", (agent_id, name.strip()))
        self._db.commit()
        return agent_id

    # -- key lifecycle -------------------------------------------------------

    def issue_key(self, agent_id: str) -> IssuedKey:
        raw = generate_raw_key()
        key_id = str(uuid.uuid4())
        self._db.execute(
            "INSERT INTO api_keys(id, agent_id, key_hash, key_prefix) VALUES (?, ?, ?, ?)",
            (key_id, agent_id, hash_key(raw), key_prefix(raw)),
        )
        self._db.commit()
        return IssuedKey(key_id=key_id, raw_key=raw, key_prefix=key_prefix(raw))

    def rotate_key(self, agent_id: str, key_id: str) -> IssuedKey:
        """Issue a fresh key and invalidate the old one (atomic)."""
        self._require_owned_key(agent_id, key_id)
        self._db.execute(
            "UPDATE api_keys SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (self._now_iso(), key_id),
        )
        issued = self.issue_key(agent_id)
        self._db.commit()
        return issued

    def revoke_key(self, agent_id: str, key_id: str) -> None:
        self._require_owned_key(agent_id, key_id)
        self._db.execute(
            "UPDATE api_keys SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (self._now_iso(), key_id),
        )
        self._db.commit()

    def list_keys(self, agent_id: str) -> list[KeyInfo]:
        rows = self._db.execute(
            "SELECT id, key_prefix, created_at, last_used_at, revoked_at "
            "FROM api_keys WHERE agent_id = ? ORDER BY created_at",
            (agent_id,),
        ).fetchall()
        return [
            KeyInfo(
                key_id=r["id"],
                key_prefix=r["key_prefix"],
                created_at=r["created_at"],
                last_used_at=r["last_used_at"],
                revoked_at=r["revoked_at"],
            )
            for r in rows
        ]

    # -- request resolution --------------------------------------------------

    def resolve(self, raw_key: str | None) -> AgentContext:
        """Resolve a presented credential to an :class:`AgentContext`.

        - ``None`` (or empty) → guest (global-only).
        - Unknown/malformed key → 401.
        - Revoked key → :class:`RevokedKeyError`.
        - Valid key → authenticated context (rate-limited).
        """
        if not raw_key:
            return AgentContext(agent_id=None, key_id=None, scope="guest")

        row = self._db.execute(
            "SELECT id, agent_id, revoked_at FROM api_keys WHERE key_hash = ?",
            (hash_key(raw_key),),
        ).fetchone()
        if row is None:
            raise AuthenticationError("unknown API key")

        if row["revoked_at"] is not None:
            raise RevokedKeyError("this API key has been revoked")

        if not self._limiter.allow(row["id"]):
            raise RateLimitError("rate limit exceeded; slow down and retry")

        self._db.execute(
            "UPDATE api_keys SET last_used_at = ? WHERE id = ?", (self._now_iso(), row["id"])
        )
        self._db.commit()
        return AgentContext(agent_id=row["agent_id"], key_id=row["id"], scope="authenticated")

    # -- helpers -------------------------------------------------------------

    def _require_owned_key(self, agent_id: str, key_id: str) -> None:
        row = self._db.execute(
            "SELECT id FROM api_keys WHERE id = ? AND agent_id = ?", (key_id, agent_id)
        ).fetchone()
        if row is None:
            raise AuthenticationError("key not found for this agent")

    @staticmethod
    def _now_iso() -> str:
        import datetime

        return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
