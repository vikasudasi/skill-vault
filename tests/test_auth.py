"""Unit tests for auth, onboarding, keys, scopes, and rate limiting (Task 4)."""

from __future__ import annotations

import pytest
from conftest import FakeEmbedder, FakeStore, insert_skill_version

from skill_vault.auth import (
    AuthService,
    FixedWindowLimiter,
    generate_raw_key,
    hash_key,
    key_prefix,
)
from skill_vault.errors import (
    AuthenticationError,
    IntegrityError,
    RateLimitError,
    RevokedKeyError,
)
from skill_vault.search import SearchService


class MutableClock:
    def __init__(self, start: float = 0.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value


def _auth(db, **kw) -> AuthService:
    rate_limit = kw.get("rate_limit", 60)
    time_fn = kw.get("time_fn")
    if time_fn is not None:
        return AuthService(db, rate_limit=rate_limit, time_fn=time_fn)
    return AuthService(db, rate_limit=rate_limit)


# --------------------------------------------------------------- key material


def test_key_format_and_hash():
    raw = generate_raw_key()
    assert raw.startswith("sv_")
    assert len(raw) > 20
    assert hash_key(raw) != raw  # never store plaintext
    assert key_prefix(raw) == raw[:11]  # 'sv_' + 8 chars
    assert hash_key(raw) == hash_key(raw)  # deterministic


def test_raw_key_not_stored(db):
    auth = _auth(db)
    result = auth.onboard("agent")
    stored = db.execute("SELECT key_hash FROM api_keys").fetchall()
    # raw key appears nowhere in the DB
    assert all(result.raw_key not in str(row["key_hash"]) for row in stored)
    assert hash_key(result.raw_key) in {row["key_hash"] for row in stored}


# ------------------------------------------------------------------- onboard


def test_onboard_issues_one_key_and_resolves(db):
    auth = _auth(db)
    result = auth.onboard("my-assistant")
    assert result.raw_key.startswith("sv_")
    ctx = auth.resolve(result.raw_key)
    assert ctx.is_authenticated
    assert ctx.agent_id == result.agent_id
    assert ctx.key_id == result.key_id


def test_agent_name_unique_per_user(db):
    """A user cannot create two agents with the same name."""
    auth = _auth(db)
    create_agent = auth.create_agent
    create_agent("planner")
    with pytest.raises(IntegrityError):
        auth.create_agent("planner")
    # ...but a different name is fine (and a differently-cased name is distinct)
    create_agent("helper")


def test_agent_name_unique_per_owner_user_but_shared_across_users(db):
    """Same name is allowed for different owning users, not for the same user."""
    auth = _auth(db)
    user_a = auth.create_user("user-a@example.com", "password123")
    user_b = auth.create_user("user-b@example.com", "password123")
    auth.create_agent("planner", owner_user_id=user_a)
    auth.create_agent("planner", owner_user_id=user_b)  # OK: different user
    with pytest.raises(IntegrityError):
        auth.create_agent("planner", owner_user_id=user_a)  # dup within user A


def test_onboard_respects_duplicate_name(db):
    """Onboarding propagates the duplicate-name IntegrityError."""
    auth = _auth(db)
    auth.onboard("dup")
    with pytest.raises(IntegrityError):
        auth.onboard("dup")


def test_super_agent_flag_resolves_from_db(db):
    """set_super_agent is surfaced through resolve(); defaults to off for new agents."""
    auth = _auth(db)
    onboard = auth.onboard("agent")

    guest = auth.resolve(None)
    assert guest.is_super_agent is False

    ctx_before = auth.resolve(onboard.raw_key)
    assert ctx_before.is_authenticated and ctx_before.is_super_agent is False

    auth.set_super_agent(onboard.agent_id, True)
    ctx_promoted = auth.resolve(onboard.raw_key)
    assert ctx_promoted.is_super_agent is True

    auth.set_super_agent(onboard.agent_id, False)
    ctx_demoted = auth.resolve(onboard.raw_key)
    assert ctx_demoted.is_super_agent is False


# ------------------------------------------------------------- scope isolation


def test_guests_get_guest_context(db):
    auth = _auth(db)
    ctx = auth.resolve(None)
    assert not ctx.is_authenticated
    assert ctx.scope == "guest"


def test_unknown_key_rejected(db):
    auth = _auth(db)
    with pytest.raises(AuthenticationError):
        auth.resolve("sv_not-a-real-key")


def test_agent_a_cannot_use_agent_b_private_skills(db):
    """Auth resolves B's key to B's identity; B's private skills are invisible to A."""
    auth_a = AuthService(db)
    auth_b = AuthService(db)
    agent_a = auth_a.create_agent("a")
    result_b = auth_b.onboard("b")

    # agent A owns a private skill (indexed).
    insert_skill_version(
        db, name="secret", description="private", visibility="personal", owner_agent_id=agent_a
    )
    store = FakeStore()
    dbgw = SearchService(db, store, FakeEmbedder())
    dbgw.reindex_all()

    # B authenticates, searches 'all' scope -> must NOT see A's private skill.
    ctx_b = auth_b.resolve(result_b.raw_key)
    assert ctx_b.is_authenticated and ctx_b.agent_id != agent_a
    dbgw_ids = [
        vid for vid, _ in dbgw.search("anything", owner_agent_id=ctx_b.agent_id, scope="all")
    ]
    assert "secret" not in dbgw_ids


# ------------------------------------------------------------------ revocation


def test_revoke_denies_key(db):
    auth = _auth(db)
    result = auth.onboard("a")
    auth.revoke_key(result.agent_id, result.key_id)
    with pytest.raises(RevokedKeyError):
        auth.resolve(result.raw_key)


def test_rotate_issues_new_and_kills_old(db):
    auth = _auth(db)
    result = auth.onboard("a")
    issued = auth.rotate_key(result.agent_id, result.key_id)

    # new key works
    ctx = auth.resolve(issued.raw_key)
    assert ctx.agent_id == result.agent_id
    assert issued.raw_key != result.raw_key

    # old key now revoked
    with pytest.raises(RevokedKeyError):
        auth.resolve(result.raw_key)

    keys = auth.list_keys(result.agent_id)
    assert len(keys) == 2
    assert sum(1 for k in keys if k.revoked_at) == 1


# ---------------------------------------------------------------- rate limiting


def test_rate_limit_blocks_excess_requests(db):
    clock = MutableClock(0.0)
    auth = _auth(db, rate_limit=2, time_fn=clock)
    result = auth.onboard("a")

    auth.resolve(result.raw_key)  # 1
    auth.resolve(result.raw_key)  # 2
    with pytest.raises(RateLimitError):
        auth.resolve(result.raw_key)  # 3 -> blocked

    # window elapses -> allowed again
    clock.value = 61.0
    assert auth.resolve(result.raw_key).is_authenticated


def test_limiter_unit():
    clock = MutableClock(0.0)
    lim = FixedWindowLimiter(2, 60, time_fn=clock)
    assert lim.allow("k") and lim.allow("k")
    assert not lim.allow("k")
    clock.value = 60.0
    assert lim.allow("k")


def test_rate_limit_per_key_is_independent():
    clock = MutableClock(0.0)
    lim = FixedWindowLimiter(1, 60, time_fn=clock)
    assert lim.allow("a")
    assert not lim.allow("a")
    assert lim.allow("b")  # different key unaffected
