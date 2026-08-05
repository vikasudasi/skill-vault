"""Config parsing coverage (Task 9, AC#1). get_settings is lru_cached, so tests
invalidate the cache before and after mutating env vars."""

from __future__ import annotations

from skill_vault.config import get_settings


def test_defaults(monkeypatch):
    # guarantee a clean env cache context (isolated from any leaked env vars)
    for var in (
        "SKILL_VAULT_DB_PATH",
        "SKILL_VAULT_VECTOR_BACKEND",
        "SKILL_VAULT_EMBED_MODEL",
        "SKILL_VAULT_TRUST_ALLOW",
        "SKILL_VAULT_CURATOR_KEY",
        "SKILL_VAULT_MCP_HOST",
        "SKILL_VAULT_MCP_PORT",
        "SKILL_VAULT_WEB_HOST",
        "SKILL_VAULT_WEB_PORT",
        "SKILL_VAULT_SEED_DIR",
        "SKILL_VAULT_PGVECTOR_DSN",
        "SKILL_VAULT_RATE_LIMIT_PER_MINUTE",
        "SKILL_VAULT_ADMIN_USERNAME",
        "SKILL_VAULT_ADMIN_PASSWORD",
    ):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    try:
        s = get_settings()
        assert s.db_path == "./skill_vault.db"
        assert s.vector_backend == "sqlite_vec"
        assert s.trust_allow == "verified,user"
        assert s.mcp_port == 8000
        assert s.web_port == 8080
        assert s.rate_limit_per_minute == 60
        assert s.admin_username == "admin"
        assert s.admin_password == "skillvault"
        assert s.curator_key is None
        assert s.pgvector_dsn is None
    finally:
        get_settings.cache_clear()


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("SKILL_VAULT_DB_PATH", "/tmp/override/v.db")
    monkeypatch.setenv("SKILL_VAULT_MCP_PORT", "9000")
    monkeypatch.setenv("SKILL_VAULT_TRUST_ALLOW", "verified")
    monkeypatch.setenv("SKILL_VAULT_CURATOR_KEY", "sk-curator")
    get_settings.cache_clear()
    try:
        s = get_settings()
        assert s.db_path == "/tmp/override/v.db"
        assert s.mcp_port == 9000
        assert s.trust_allow == "verified"
        assert s.curator_key == "sk-curator"
    finally:
        get_settings.cache_clear()


def test_empty_optional_env_yields_none(monkeypatch):
    monkeypatch.setenv("SKILL_VAULT_CURATOR_KEY", "")
    monkeypatch.setenv("SKILL_VAULT_PGVECTOR_DSN", "")
    get_settings.cache_clear()
    try:
        s = get_settings()
        assert s.curator_key is None
        assert s.pgvector_dsn is None
    finally:
        get_settings.cache_clear()
