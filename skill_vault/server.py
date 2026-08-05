"""MCP server assembly — builds services and registers the Skill Vault tool surface."""

from __future__ import annotations

from fastmcp import FastMCP

from skill_vault.bootstrap import Services, build_services
from skill_vault.tools import register_tools


def create_server(services: Services | None = None) -> FastMCP:
    """Create a configured Skill Vault MCP server.

    ``services`` may be supplied by callers (tests, web app) to share a single
    connection; otherwise a full stack is bootstrapped from settings.
    """
    services = services or build_services()
    server = FastMCP("skill-vault")
    register_tools(server, services.registry)
    return server


__all__ = ["Services", "build_services", "create_server"]
