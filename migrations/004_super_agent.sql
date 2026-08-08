-- Add super-agent flag to agents.
-- A super agent's API key may publish/update GLOBAL skills via the MCP tools;
-- those global publishes are auto-signed with the curator key so they resolve
-- to tier 'verified'. Default 0 = normal agent (all existing guards unchanged).

ALTER TABLE agents
    ADD COLUMN is_super_agent INTEGER NOT NULL DEFAULT 0;
