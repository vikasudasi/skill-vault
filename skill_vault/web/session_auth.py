from __future__ import annotations

import sqlite3

from fastapi import HTTPException, Request

from skill_vault.bootstrap import Services


def require_user(request: Request) -> sqlite3.Row:
    cookie_name = getattr(request.app.state, "session_cookie", "sv_session")
    token = request.cookies.get(cookie_name)
    services = request.app.state.services
    if not isinstance(services, Services):
        raise TypeError("app.state.services is not configured")
    user = services.auth.get_user_by_session(token)
    if user is None:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    request.state.user = user
    return user
