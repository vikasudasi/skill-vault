from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from skill_vault.bootstrap import Services
from skill_vault.db import locked
from skill_vault.errors import SkillVaultError
from skill_vault.models import SkillCard, SkillInput
from skill_vault.web.admin import require_admin

router = APIRouter()
_PAGE_SIZE = 10


@router.get(
    "/dashboard",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)],
)
def dashboard_home(request: Request) -> Response:
    services = _services(request)
    templates = _templates(request)
    with locked():
        agents = services.db.execute(
            "SELECT id, name, created_at FROM agents ORDER BY created_at DESC"
        ).fetchall()
    return templates.TemplateResponse(
        request,
        "agents_overview.html",
        {"agents": agents},
    )


@router.get(
    "/dashboard/onboard",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)],
)
def onboard_form(request: Request) -> Response:
    return _templates(request).TemplateResponse(request, "onboard.html")


@router.post(
    "/dashboard/onboard",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)],
)
def onboard_submit(request: Request, name: str = Form(...)) -> Response:
    services = _services(request)
    try:
        with locked():
            result = services.auth.onboard(name)
    except SkillVaultError as exc:
        _raise_http(exc)
    return _templates(request).TemplateResponse(
        request,
        "onboard_done.html",
        {"agent_id": result.agent_id,
            "key_id": result.key_id,
            "raw_key": result.raw_key,
            "key_prefix": result.key_prefix,
            "title": "Agent Onboarded",
        },
    )


@router.get(
    "/agents/{agent_id}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)],
)
def agent_dashboard(
    request: Request,
    agent_id: str,
    tab: str = Query(default="personal"),
    q: str = Query(default=""),
    page: int = Query(default=1),
) -> Response:
    services = _services(request)
    templates = _templates(request)
    current_page = _normalize_page(page)
    query = q.strip()
    active_tab = "global" if tab == "global" else "personal"

    try:
        with locked():
            agent_row = services.db.execute(
                "SELECT id, name FROM agents WHERE id = ?",
                (agent_id,),
            ).fetchone()
            if agent_row is None:
                raise HTTPException(status_code=404, detail="Agent not found")
            personal_skills = services.registry.admin_list_my(agent_id)
            keys = services.auth.list_keys(agent_id)
            global_skills, has_next = _browse_page(services, query, current_page)
    except SkillVaultError as exc:
        _raise_http(exc)

    return templates.TemplateResponse(
        request,
        "agent_dashboard.html",
        {"agent": agent_row,
            "agent_id": agent_id,
            "personal_skills": personal_skills,
            "keys": keys,
            "active_tab": active_tab,
            "global_skills": global_skills,
            "q": query,
            "page": current_page,
            "has_next": has_next,
            "prev_page": current_page - 1,
            "next_page": current_page + 1,
        },
    )


@router.get(
    "/agents/{agent_id}/skills/new",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)],
)
def new_skill_form(request: Request, agent_id: str) -> Response:
    return _templates(request).TemplateResponse(
        request,
        "skill_form.html",
        {"title": "Publish Skill",
            "submit_label": "Publish",
            "action_url": f"/agents/{agent_id}/skills",
            "agent_id": agent_id,
            "mode": "new",
            "skill": None,
            "visibility": "personal",
            "tags": "",
            "triggers": "",
        },
    )


@router.post(
    "/agents/{agent_id}/skills",
    dependencies=[Depends(require_admin)],
)
def publish_skill(
    request: Request,
    agent_id: str,
    name: str = Form(...),
    description: str = Form(...),
    tags: str = Form(default=""),
    triggers: str = Form(default=""),
    body: str = Form(...),
    visibility: str = Form(...),
) -> RedirectResponse:
    services = _services(request)
    skill = _skill_input(name, description, tags, triggers, body)
    try:
        with locked():
            services.registry.admin_publish(agent_id=agent_id, skill=skill, visibility=visibility)
    except SkillVaultError as exc:
        _raise_http(exc)
    return RedirectResponse(url=f"/agents/{agent_id}", status_code=303)


@router.get(
    "/agents/{agent_id}/skills/{skill_id}/edit",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)],
)
def edit_skill_form(request: Request, agent_id: str, skill_id: str) -> Response:
    services = _services(request)
    try:
        with locked():
            detail = services.registry.admin_get(agent_id=agent_id, identifier=skill_id)
            visibility = _skill_visibility(services, detail.id)
    except SkillVaultError as exc:
        _raise_http(exc)
    return _templates(request).TemplateResponse(
        request,
        "skill_form.html",
        {"title": "Update Skill",
            "submit_label": "Save Changes",
            "action_url": f"/agents/{agent_id}/skills/{skill_id}",
            "agent_id": agent_id,
            "mode": "edit",
            "skill": detail,
            "visibility": visibility,
            "tags": ", ".join(detail.tags),
            "triggers": _triggers_for(services, detail.id),
        },
    )


@router.post(
    "/agents/{agent_id}/skills/{skill_id}",
    dependencies=[Depends(require_admin)],
)
def update_skill(
    request: Request,
    agent_id: str,
    skill_id: str,
    name: str = Form(...),
    description: str = Form(...),
    tags: str = Form(default=""),
    triggers: str = Form(default=""),
    body: str = Form(...),
) -> RedirectResponse:
    services = _services(request)
    skill = _skill_input(name, description, tags, triggers, body)
    try:
        with locked():
            services.registry.admin_update(agent_id=agent_id, identifier=skill_id, skill=skill)
    except SkillVaultError as exc:
        _raise_http(exc)
    return RedirectResponse(url=f"/agents/{agent_id}", status_code=303)


@router.post(
    "/agents/{agent_id}/skills/{skill_id}/delete",
    dependencies=[Depends(require_admin)],
)
def delete_skill(request: Request, agent_id: str, skill_id: str) -> RedirectResponse:
    services = _services(request)
    try:
        with locked():
            services.registry.admin_delete(agent_id=agent_id, identifier=skill_id)
    except SkillVaultError as exc:
        _raise_http(exc)
    return RedirectResponse(url=f"/agents/{agent_id}", status_code=303)


@router.post(
    "/agents/{agent_id}/keys/{key_id}/rotate",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)],
)
def rotate_key(request: Request, agent_id: str, key_id: str) -> Response:
    services = _services(request)
    try:
        with locked():
            issued = services.auth.rotate_key(agent_id=agent_id, key_id=key_id)
    except SkillVaultError as exc:
        _raise_http(exc)
    return _templates(request).TemplateResponse(
        request,
        "onboard_done.html",
        {"agent_id": agent_id,
            "key_id": issued.key_id,
            "raw_key": issued.raw_key,
            "key_prefix": issued.key_prefix,
            "title": "Rotated API Key",
        },
    )


@router.post(
    "/agents/{agent_id}/keys/{key_id}/revoke",
    dependencies=[Depends(require_admin)],
)
def revoke_key(request: Request, agent_id: str, key_id: str) -> RedirectResponse:
    services = _services(request)
    try:
        with locked():
            services.auth.revoke_key(agent_id=agent_id, key_id=key_id)
    except SkillVaultError as exc:
        _raise_http(exc)
    return RedirectResponse(url=f"/agents/{agent_id}", status_code=303)


@router.get("/browse", response_class=HTMLResponse)
def browse(
    request: Request,
    q: str = Query(default=""),
    page: int = Query(default=1),
) -> Response:
    services = _services(request)
    query = q.strip()
    current_page = _normalize_page(page)
    try:
        with locked():
            cards, has_next = _browse_page(services, query, current_page)
    except SkillVaultError as exc:
        _raise_http(exc)
    return _templates(request).TemplateResponse(
        request,
        "browse.html",
        {"q": query,
            "page": current_page,
            "prev_page": current_page - 1,
            "next_page": current_page + 1,
            "has_next": has_next,
            "skills": cards,
        },
    )


@router.get("/skills/{skill_id}", response_class=HTMLResponse)
def skill_detail(request: Request, skill_id: str) -> Response:
    services = _services(request)
    try:
        with locked():
            detail = services.registry.get(identifier=skill_id, agent_key=None)
            created_at = _created_at_for(services, detail.id, detail.version)
    except SkillVaultError as exc:
        _raise_http(exc)
    return _templates(request).TemplateResponse(
        request,
        "skill_detail.html",
        {"skill": detail,
            "created_at": created_at,
            "integrity_status": "OK",
        },
    )


def _browse_page(services: Services, query: str, page: int) -> tuple[list[SkillCard], bool]:
    if query:
        needed = page * _PAGE_SIZE + 1
        cards = services.registry.search(
            query=query,
            scope="global",
            limit=needed,
            agent_key=None,
        )
        start = (page - 1) * _PAGE_SIZE
        page_cards = cards[start : start + _PAGE_SIZE]
        return page_cards, len(cards) > (start + _PAGE_SIZE)
    offset = (page - 1) * _PAGE_SIZE
    cards = services.registry.list_global(limit=_PAGE_SIZE + 1, offset=offset)
    return cards[:_PAGE_SIZE], len(cards) > _PAGE_SIZE


def _created_at_for(services: Services, skill_id: str, version: int) -> str | None:
    row = services.db.execute(
        "SELECT created_at FROM skill_versions WHERE skill_id = ? AND version = ?",
        (skill_id, version),
    ).fetchone()
    return str(row["created_at"]) if row is not None else None


def _triggers_for(services: Services, skill_id: str) -> str:
    row = services.db.execute(
        "SELECT triggers FROM skill_versions WHERE skill_id = ? ORDER BY version DESC LIMIT 1",
        (skill_id,),
    ).fetchone()
    if row is None:
        return ""
    return ", ".join(_comma_list(str(row["triggers"])))


def _skill_visibility(services: Services, skill_id: str) -> str:
    row = services.db.execute("SELECT visibility FROM skills WHERE id = ?", (skill_id,)).fetchone()
    if row is None:
        return "personal"
    visibility = str(row["visibility"])
    return visibility if visibility in {"global", "personal"} else "personal"


def _comma_list(raw: str) -> list[str]:
    text = raw.strip()
    if text.startswith("[") and text.endswith("]"):
        import json

        try:
            value = json.loads(text)
        except ValueError:
            value = []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _normalize_page(page: int) -> int:
    return page if page > 0 else 1


def _skill_input(
    name: str,
    description: str,
    tags: str,
    triggers: str,
    body: str,
) -> SkillInput:
    return SkillInput(
        name=name,
        description=description,
        tags=_comma_list(tags),
        triggers=_comma_list(triggers),
        body=body,
        meta={},
    )


def _services(request: Request) -> Services:
    services = request.app.state.services
    if not isinstance(services, Services):
        raise TypeError("app.state.services is not configured")
    return services


def _templates(request: Request) -> Jinja2Templates:
    templates = request.app.state.templates
    if not isinstance(templates, Jinja2Templates):
        raise TypeError("app.state.templates is not configured")
    return templates


def _raise_http(exc: SkillVaultError) -> NoReturn:
    raise HTTPException(
        status_code=exc.http_status,
        detail=f"{exc.code}: {exc.message}",
    ) from exc
