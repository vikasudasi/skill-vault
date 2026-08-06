-- Skill Vault — 001_baseline.sql
-- Baseline schema: agents, api_keys, skills, skill_versions, trust, tags, skill_tags.
-- Conventions: UUID PKs stored as TEXT; ISO-8601 UTC timestamps; WAL; foreign_keys ON.
-- Migration runner applies forward-only migrations; this is the baseline.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- agents : per-agent identity (one API-key holder / assistant)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agents (
    id          TEXT PRIMARY KEY,                    -- UUID v4
    name        TEXT NOT NULL,
    owner_user_id TEXT REFERENCES users(id) ON DELETE SET NULL, -- NULL => seed/system
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_agents_owner_user ON agents(owner_user_id);

-- ---------------------------------------------------------------------------
-- users : dashboard accounts
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,                  -- UUID v4
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,                     -- pbkdf2 record
    superuser     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ---------------------------------------------------------------------------
-- api_keys : hash-only key storage (raw key shown once at onboarding, never saved)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS api_keys (
    id            TEXT PRIMARY KEY,                  -- UUID v4
    agent_id      TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    key_hash      TEXT NOT NULL UNIQUE,              -- sha256 hex of the raw key
    key_prefix    TEXT NOT NULL,                     -- first 8 chars, for display/rotation
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_used_at  TEXT,
    revoked_at    TEXT                               -- non-null => revoked
);
CREATE INDEX IF NOT EXISTS idx_api_keys_agent ON api_keys(agent_id);

-- ---------------------------------------------------------------------------
-- sessions : hash-only browser sessions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,                    -- UUID v4
    token       TEXT NOT NULL UNIQUE,                -- sha256 hex of raw session token
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    expires_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);

-- ---------------------------------------------------------------------------
-- skills : logical skill; versioned content lives in skill_versions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS skills (
    id                  TEXT PRIMARY KEY,            -- UUID v4 (stable across versions)
    name                TEXT NOT NULL,
    owner_agent_id      TEXT REFERENCES agents(id) ON DELETE SET NULL,  -- NULL => global/seed
    visibility          TEXT NOT NULL DEFAULT 'personal'
                        CHECK (visibility IN ('global','personal','team')),
    current_version_id  TEXT REFERENCES skill_versions(id),  -- points to latest released version
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at          TEXT,                        -- soft-delete marker (keeps version history)
    UNIQUE (name, owner_agent_id)
);
CREATE INDEX IF NOT EXISTS idx_skills_owner  ON skills(owner_agent_id);
CREATE INDEX IF NOT EXISTS idx_skills_vis    ON skills(visibility);

-- ---------------------------------------------------------------------------
-- skill_versions : immutable, content-addressed versions of a SKILL.md
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS skill_versions (
    id              TEXT PRIMARY KEY,                -- UUID v4
    skill_id        TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    version         INTEGER NOT NULL,                -- 1-based, monotonic per skill
    content_hash    TEXT NOT NULL,                   -- sha256 of canonical serialization
    name            TEXT NOT NULL,                   -- denormalized for search
    description     TEXT NOT NULL,                   -- one-line, for card + embedding
    tags            TEXT NOT NULL DEFAULT '[]',      -- JSON array of strings
    triggers        TEXT NOT NULL DEFAULT '[]',      -- JSON array of trigger phrases
    meta_json       TEXT NOT NULL DEFAULT '{}',      -- complexity, time_estimate, prerequisites, source
    body            TEXT NOT NULL,                   -- full SKILL.md markdown body
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (skill_id, version)
);
CREATE INDEX IF NOT EXISTS idx_skill_versions_skill ON skill_versions(skill_id);
CREATE INDEX IF NOT EXISTS idx_skill_versions_hash ON skill_versions(content_hash);

-- ---------------------------------------------------------------------------
-- trust : trust tier + signature record per skill version
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trust (
    id                  TEXT PRIMARY KEY,            -- UUID v4
    skill_version_id    TEXT NOT NULL UNIQUE REFERENCES skill_versions(id) ON DELETE CASCADE,
    tier                TEXT NOT NULL
                        CHECK (tier IN ('verified','user','public')),
    signed_by           TEXT,                        -- curator/verifier identity
    signature           TEXT,                        -- ed25519 signature (base64) over content_hash
    public_key          TEXT,                        -- verifier ed25519 public key (base64)
    verified_at         TEXT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_trust_tier ON trust(tier);

-- ---------------------------------------------------------------------------
-- tags : normalized tags (optional; search may also read skill_versions.tags JSON)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tags (
    id   TEXT PRIMARY KEY,                           -- UUID v4
    name TEXT NOT NULL UNIQUE
);

-- ---------------------------------------------------------------------------
-- skill_tags : join skill_version_id <-> tag_id
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS skill_tags (
    skill_version_id TEXT NOT NULL REFERENCES skill_versions(id) ON DELETE CASCADE,
    tag_id           TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (skill_version_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_skill_tags_tag ON skill_tags(tag_id);

-- ---------------------------------------------------------------------------
-- schema_migrations : applied-migration ledger for the forward-only runner
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,                  -- migration number
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Seed the ledger with baseline applied (runner reconciles via applied versions).
INSERT OR IGNORE INTO schema_migrations (version) VALUES (1);
