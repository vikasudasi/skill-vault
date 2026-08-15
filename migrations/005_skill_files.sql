CREATE TABLE IF NOT EXISTS skill_version_files (
    id TEXT PRIMARY KEY,
    skill_version_id TEXT NOT NULL REFERENCES skill_versions(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('script','reference')),
    filename TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(skill_version_id, filename)
);
CREATE INDEX IF NOT EXISTS idx_svf_skill_version ON skill_version_files(skill_version_id);
