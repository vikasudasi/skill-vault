from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from skill_vault.bootstrap import Services, build_services
from skill_vault.config import get_settings
from skill_vault.web.admin import AdminAuth
from skill_vault.web.dashboard import router


def create_app(services: Services | None = None, admin: AdminAuth | None = None) -> FastAPI:
    app = FastAPI(title="Skill Vault")
    services = services or build_services()
    settings = get_settings()
    admin = admin or AdminAuth(settings.admin_username, settings.admin_password)
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    app.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).parent / "static")),
        name="static",
    )
    app.state.services = services
    app.state.admin_auth = admin
    app.state.templates = templates

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)

    return app
