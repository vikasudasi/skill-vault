from __future__ import annotations

from fastmcp import FastMCP

from skill_vault import tools
from skill_vault.models import SkillCard, SkillDetail, SkillInput
from skill_vault.tools import DeleteResult, PublishResult, VerifyResult


def create_server() -> FastMCP:
    server = FastMCP("skill-vault")

    @server.tool()
    def search_skills(
        query: str,
        scope: str = "global",
        limit: int = 10,
        min_trust: str | None = None,
        agent_key: str | None = None,
    ) -> list[SkillCard]:
        return tools.search_skills(
            query=query,
            scope=scope,
            limit=limit,
            min_trust=min_trust,
            agent_key=agent_key,
        )

    @server.tool()
    def get_skill(id: str, agent_key: str | None = None) -> SkillDetail:
        return tools.get_skill(id=id, agent_key=agent_key)

    @server.tool()
    def publish_skill(
        skill: SkillInput,
        visibility: str = "personal",
        *,
        agent_key: str,
    ) -> PublishResult:
        return tools.publish_skill(
            skill=skill,
            visibility=visibility,
            agent_key=agent_key,
        )

    @server.tool()
    def update_skill(id: str, skill: SkillInput, agent_key: str) -> PublishResult:
        return tools.update_skill(id=id, skill=skill, agent_key=agent_key)

    @server.tool()
    def list_my_skills(agent_key: str, scope: str = "all") -> list[SkillCard]:
        return tools.list_my_skills(agent_key=agent_key, scope=scope)

    @server.tool()
    def delete_skill(id: str, agent_key: str) -> DeleteResult:
        return tools.delete_skill(id=id, agent_key=agent_key)

    @server.tool()
    def verify_skill(id: str) -> VerifyResult:
        return tools.verify_skill(id=id)

    return server
