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

import datetime
import hashlib
import secrets
import sqlite3
import time as _time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from skill_vault.db import locked
from skill_vault.errors import (
    AuthenticationError,
    RateLimitError,
    RevokedKeyError,
)

KEY_PREFIX_LEADER = "sv_"
PASSWORD_SCHEME = "pbkdf2"
PASSWORD_ITERATIONS = 200_000
SESSION_TTL_DAYS = 30


def generate_raw_key() -> str:
    """Return a new high-entropy API key like ``sv_<43 url-safe chars>``."""
    return f"{KEY_PREFIX_LEADER}{secrets.token_urlsafe(32)}"


def hash_key(raw_key: str) -> str:
    """One-way hash of a raw key, as stored at rest."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def hash_password(password: str, *, iterations: int = PASSWORD_ITERATIONS) -> str:
    """Return a PBKDF2 password record."""
    if not password:
        raise AuthenticationError("password must not be empty")
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{PASSWORD_SCHEME}${iterations}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against a PBKDF2 record."""
    if not password or not stored:
        return False
    parts = stored.split("$")
    if len(parts) != 4:
        return False
    scheme, iterations_raw, salt_hex, hash_hex = parts
    if scheme != PASSWORD_SCHEME:
        return False
    try:
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return secrets.compare_digest(actual, expected)


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

    def onboard(self, name: str, owner_user_id: str | None = None) -> OnboardResult:
        """Create an agent and issue its first key (shown once)."""
        agent_id = self.create_agent(name, owner_user_id=owner_user_id)
        issued = self.issue_key(agent_id)
        return OnboardResult(
            agent_id=agent_id,
            key_id=issued.key_id,
            raw_key=issued.raw_key,
            key_prefix=issued.key_prefix,
        )

    def create_agent(self, name: str, owner_user_id: str | None = None) -> str:
        if not name or not name.strip():
            raise AuthenticationError("agent name must not be empty")
        agent_id = str(uuid.uuid4())
        with locked():
            self._db.execute(
                "INSERT INTO agents(id, name, owner_user_id) VALUES (?, ?, ?)",
                (agent_id, name.strip(), owner_user_id),
            )
            self._db.commit()
        return agent_id

    # -- key lifecycle -------------------------------------------------------

    def issue_key(self, agent_id: str) -> IssuedKey:
        raw = generate_raw_key()
        key_id = str(uuid.uuid4())
        with locked():
            self._db.execute(
                "INSERT INTO api_keys(id, agent_id, key_hash, key_prefix) VALUES (?, ?, ?, ?)",
                (key_id, agent_id, hash_key(raw), key_prefix(raw)),
            )
            self._db.commit()
        return IssuedKey(key_id=key_id, raw_key=raw, key_prefix=key_prefix(raw))

    def rotate_key(self, agent_id: str, key_id: str) -> IssuedKey:
        """Issue a fresh key and invalidate the old one (atomic)."""
        with locked():
            self._require_owned_key(agent_id, key_id)
            self._db.execute(
                "UPDATE api_keys SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (self._now_iso(), key_id),
            )
            issued = self._issue_key_locked(agent_id)
            self._db.commit()
        return issued

    def revoke_key(self, agent_id: str, key_id: str) -> None:
        with locked():
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

        with locked():
            self._db.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE id = ?", (self._now_iso(), row["id"])
            )
            self._db.commit()
        return AgentContext(agent_id=row["agent_id"], key_id=row["id"], scope="authenticated")

    # -- user/session auth ----------------------------------------------------

    def create_user(self, email: str, password: str, superuser: int = 0) -> str:
        normalized_email = self._normalize_email(email)
        user_id = str(uuid.uuid4())
        password_record = hash_password(password)
        try:
            with locked():
                self._db.execute(
                    "INSERT INTO users(id, email, password_hash, superuser) VALUES (?, ?, ?, ?)",
                    (user_id, normalized_email, password_record, int(bool(superuser))),
                )
                self._db.commit()
        except sqlite3.IntegrityError as exc:
            raise AuthenticationError("email already exists") from exc
        return user_id

    def verify_credentials(self, email: str, password: str) -> sqlite3.Row:
        normalized_email = self._normalize_email(email)
        row = self._db.execute(
            "SELECT id, email, password_hash, superuser, created_at, updated_at "
            "FROM users WHERE email = ?",
            (normalized_email,),
        ).fetchone()
        if row is None or not verify_password(password, row["password_hash"]):
            raise AuthenticationError("invalid credentials")
        return cast(sqlite3.Row, row)

    def create_session(self, user_id: str) -> str:
        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_key(raw_token)
        session_id = str(uuid.uuid4())
        expires_at = (
            datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=SESSION_TTL_DAYS)
        ).strftime(
            "%Y-%m-%dT%H:%M:%SZ",
        )
        with locked():
            self._db.execute(
                "INSERT INTO sessions(id, token, user_id, expires_at) VALUES (?, ?, ?, ?)",
                (session_id, token_hash, user_id, expires_at),
            )
            self._db.commit()
        return raw_token

    def get_user_by_session(self, token: str | None) -> sqlite3.Row | None:
        if not token:
            return None
        now_iso = self._now_iso()
        row = self._db.execute(
            "SELECT u.id, u.email, u.superuser, u.created_at, u.updated_at "
            "FROM sessions s "
            "JOIN users u ON u.id = s.user_id "
            "WHERE s.token = ? AND s.expires_at > ?",
            (hash_key(token), now_iso),
        ).fetchone()
        return cast(sqlite3.Row | None, row)

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        with locked():
            self._db.execute("DELETE FROM sessions WHERE token = ?", (hash_key(token),))
            self._db.commit()

    def upsert_superuser(self, username: str, password: str) -> str:
        normalized_email = self._normalize_email(username)
        row = self._db.execute(
            "SELECT id FROM users WHERE email = ?",
            (normalized_email,),
        ).fetchone()
        password_record = hash_password(password)
        if row is None:
            user_id = str(uuid.uuid4())
            with locked():
                self._db.execute(
                    "INSERT INTO users(id, email, password_hash, superuser) VALUES (?, ?, ?, 1)",
                    (user_id, normalized_email, password_record),
                )
                self._db.commit()
            return user_id
        user_id = str(row["id"])
        with locked():
            self._db.execute(
                "UPDATE users SET password_hash = ?, superuser = 1, updated_at = ? WHERE id = ?",
                (password_record, self._now_iso(), user_id),
            )
            self._db.commit()
        return user_id

    # -- helpers -------------------------------------------------------------

    def _issue_key_locked(self, agent_id: str) -> IssuedKey:
        raw = generate_raw_key()
        key_id = str(uuid.uuid4())
        self._db.execute(
            "INSERT INTO api_keys(id, agent_id, key_hash, key_prefix) VALUES (?, ?, ?, ?)",
            (key_id, agent_id, hash_key(raw), key_prefix(raw)),
        )
        return IssuedKey(key_id=key_id, raw_key=raw, key_prefix=key_prefix(raw))

    def _require_owned_key(self, agent_id: str, key_id: str) -> None:
        row = self._db.execute(
            "SELECT id FROM api_keys WHERE id = ? AND agent_id = ?", (key_id, agent_id)
        ).fetchone()
        if row is None:
            raise AuthenticationError("key not found for this agent")

    @staticmethod
    def _normalize_email(email: str) -> str:
        normalized = email.strip().lower()
        if not normalized:
            raise AuthenticationError("email must not be empty")
        return normalized

    @staticmethod
    def _now_iso() -> str:
        return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
