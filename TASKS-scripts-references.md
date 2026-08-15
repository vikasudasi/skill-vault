# scripts/references feature — local task tracker
> Tasks for adding `scripts/` and `references/` support to skill-vault
> TM server unreachable, stored locally for later sync.

## Task 1: Schema & model layer
- [ ] Migration 002.sql → `skill_version_files` table
- [ ] Pydantic models: SkillFile, SkillInputFile, SkillFileDetail
- [ ] Extend SkillInput/SkillDetail with files field
- [ ] Update canonical_payload to include files

## Task 2: Trust layer update
- [ ] `canonical_payload()` accepts files param
- [ ] Content hash covers files
- [ ] Ensure backward compatibility (empty files list = same hash)

## Task 3: MCP tools + service layer
- [ ] upload_skill_file tool (kind, filename, content)
- [ ] list_skill_files tool (metadata, no content)
- [ ] get_skill_file tool (full content)
- [ ] Update get_skill to surface file metadata in SkillDetail
- [ ] Update publish/update to accept and store files
- [ ] Cascade delete files on version/agent delete

## Task 4: Search
- [ ] Index file names/basics for search
- [ ] Optionally index script content

## Task 5: Tests + CI
- [ ] File CRUD tests
- [ ] Hash integrity tests with files
- [ ] File-aware search tests
- [ ] Web dashboard tests

## Task 6: Web dashboard
- [ ] Show attached files on skill detail page
- [ ] File upload UI
- [ ] Highlight.js for code files