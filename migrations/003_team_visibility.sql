-- Rebuild skills table to widen visibility CHECK constraint to include 'team'.
-- SQLite cannot ALTER CHECK constraints in place.

CREATE TEMP TABLE IF NOT EXISTS _skills_fk_state(value INTEGER NOT NULL);
DELETE FROM _skills_fk_state;
INSERT INTO _skills_fk_state(value)
SELECT foreign_keys FROM pragma_foreign_keys;

PRAGMA foreign_keys = OFF;

BEGIN;

CREATE TABLE skills_new (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    owner_agent_id      TEXT REFERENCES agents(id) ON DELETE SET NULL,
    visibility          TEXT NOT NULL DEFAULT 'personal'
                        CHECK (visibility IN ('global','personal','team')),
    current_version_id  TEXT REFERENCES skill_versions(id),
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    deleted_at          TEXT,
    UNIQUE (name, owner_agent_id)
);

INSERT INTO skills_new (
    id,
    name,
    owner_agent_id,
    visibility,
    current_version_id,
    created_at,
    updated_at,
    deleted_at
)
SELECT
    id,
    name,
    owner_agent_id,
    visibility,
    current_version_id,
    created_at,
    updated_at,
    deleted_at
FROM skills;

DROP TABLE skills;
ALTER TABLE skills_new RENAME TO skills;

CREATE INDEX IF NOT EXISTS idx_skills_owner ON skills(owner_agent_id);
CREATE INDEX IF NOT EXISTS idx_skills_vis ON skills(visibility);

COMMIT;

-- Baseline/runtime contract expects FK enforcement enabled after migration.
PRAGMA foreign_keys = ON;
