from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from skill_vault.bootstrap import Services, build_services
from skill_vault.config import get_settings
from skill_vault.web.admin import AdminAuth
from skill_vault.web.dashboard import router

# Render skill (markdown) bodies to safe HTML. Raw HTML inside skill content is
# not passed through, so a malicious skill can't inject markup into the dashboard.
_md = MarkdownIt("commonmark", {"html": False}).enable("table")


def create_app(services: Services | None = None, admin: AdminAuth | None = None) -> FastAPI:
    app = FastAPI(title="Skill Vault")
    services = services or build_services()
    settings = get_settings()
    admin = admin or AdminAuth(settings.admin_username, settings.admin_password)
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    templates.env.filters["markdown"] = lambda text: _md.render(text) if text else ""

    app.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).parent / "static")),
        name="static",
    )
    app.state.services = services
    app.state.admin_auth = admin
    app.state.templates = templates
    app.state.session_cookie = "sv_session"
    app.state.session_cookie_secure = _env_bool("SKILL_VAULT_SESSION_COOKIE_SECURE", default=False)
    services.auth.upsert_superuser(settings.admin_username, settings.admin_password)

    @app.middleware("http")
    async def init_request_user(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.user = None
        return await call_next(request)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)

    return app


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
