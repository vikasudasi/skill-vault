# SPEC: scripts + references support for Skill Vault

## Overview

Add `scripts/` and `references/` file attachment capabilities to the Skill Vault
MCP server, per the Agent Skills specification (agentskills.io). Each skill version
can have zero or more attached files of kind `script` or `reference`, stored in a
new SQL table and surfaced through new MCP tools.

## File Structure (changes)

```
skill_vault/
  models.py          ← add SkillFile, SkillInputFile; extend SkillInput, SkillDetail
  service.py         ← add file CRUD methods
  tools.py           ← add upload_skill_file, list_skill_files, get_skill_file tools
  trust.py           ← extend canonical_payload() with optional files param
migrations/
  002_skill_files.sql  ← (new) skill_version_files table
tests/
  test_skill_files.py  ← (new) file CRUD + hash + search tests
```

## Detailed Changes

### 1. Migration: `migrations/002_skill_files.sql`

```sql
CREATE TABLE IF NOT EXISTS skill_version_files (
    id              TEXT PRIMARY KEY,
    skill_version_id TEXT NOT NULL REFERENCES skill_versions(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL CHECK (kind IN ('script', 'reference')),
    filename        TEXT NOT NULL,
    content         TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(skill_version_id, filename)
);
CREATE INDEX IF NOT EXISTS idx_svf_skill_version ON skill_version_files(skill_version_id);
```

### 2. Models: `models.py`

Add these dataclasses and pydantic models:

```python
@dataclass(slots=True)
class SkillFile:
    id: str
    skill_version_id: str
    kind: str  # 'script' | 'reference'
    filename: str
    content: str
    content_hash: str
    created_at: str


class SkillInputFile(BaseModel):
    kind: str = Field(..., pattern=r"^(script|reference)$")
    filename: str = Field(..., min_length=1, max_length=255)
    content: str


class SkillFileMeta(BaseModel):
    """Lightweight file metadata returned in lists and detail responses (no content)."""

    id: str
    kind: str
    filename: str
    content_hash: str
```

Extend `SkillInput` with optional `files: list[SkillInputFile] = Field(default_factory=list)`.

Extend `SkillDetail` with optional `files: list[SkillFileMeta] = Field(default_factory=list)`.

### 3. Trust: `trust.py`

Extend canonical_payload() to accept optional `files: list[dict] | None = None`.

When `files` is provided, add a sorted file section to the serialized payload:
```python
if files:
    payload["files"] = sorted(files, key=lambda f: f["filename"])
```

This ensures backward compatibility: empty/missing files list produces the same hash as before.

### 4. Service: `service.py`

Add methods to `RegistryService`:

- `add_skill_file(skill_version_id, kind, filename, content, agent_key=None) -> SkillFile`
  - Validates agent_key owns the skill version
  - Computes sha256 content_hash of file content
  - Inserts into skill_version_files
  - Rebuilds skill's content_hash with new files
  - Returns SkillFile

- `list_skill_files(skill_version_id, agent_key=None) -> list[SkillFileMeta]`
  - Returns metadata without content
  - Public reads allowed for global/team visibility skills

- `get_skill_file(file_id, agent_key=None) -> SkillFile`
  - Returns full content
  - Respects visibility + agent auth

- `remove_skill_file(file_id, agent_key=None) -> None`
  - Validates ownership, deletes, updates parent hash

- `_load_files(version_id) -> list[SkillFile]`
  - Internal helper to load all files for a version

- Update `_build_payload()` to include files when computing canonical content_hash
- Update `_remove_skill_content()` to cascade delete files (or rely on ON DELETE CASCADE)
- Update `publish_skill()` to accept and store files from SkillInput
- Update `update_skill()` to accept and merge files

### 5. MCP Tools: `tools.py`

Register these new tools:

- `upload_skill_file(skill_version_id, kind, filename, content, agent_key) -> SkillFile`
- `list_skill_files(skill_version_id, agent_key) -> list[SkillFileMeta]`
- `get_skill_file(file_id, agent_key) -> SkillFile`

Update existing `publish_skill` and `update_skill` tools to accept optional `files` parameter.

Update `get_skill` tool results to include file metadata.

### 6. Web Dashboard

Add a "Attached Files" section to the skill detail template showing file names by kind.
New endpoint: `GET /skills/<id>/version/<ver>/files` returns JSON.

### 7. Tests: `tests/test_skill_files.py`

- File CRUD lifecycle (add, list, get, remove)
- Hash integrity: skill hash changes when files are added/removed
- Backward compat: publishing with no files produces same hash as before
- Auth: unauthorized agent cannot add/get files
- Cascade: deleting a version deletes its files (ON DELETE CASCADE)

## Implementation Order

1. Migration + models → service file CRUD → trust extension → tools → web → tests
2. Run `pytest tests/test_skill_files.py -v` after each step
3. Final: `pytest tests/ -v --co` to confirm no regressions

## Key Constraints

- Do NOT destabilize existing publish/update/get/search operations
- Empty files list = same content_hash as before (backward compat)
- Files are tied to a specific skill version (immutable once published, add-only per version)
- Use ON DELETE CASCADE from skill_versions to skill_version_files