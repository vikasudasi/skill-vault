from __future__ import annotations

import base64
import binascii
import secrets
from collections.abc import Callable
from typing import NoReturn

from fastapi import HTTPException, Request


class AdminAuth:
    def __init__(
        self,
        username: str,
        password: str,
        *,
        verify: Callable[[str, str], bool] | None = None,
    ) -> None:
        self._username = username
        self._password = password
        self._verify_callback = verify

    def verify(self, username: str, password: str) -> bool:
        if self._verify_callback is not None:
            return self._verify_callback(username, password)
        return secrets.compare_digest(username, self._username) and secrets.compare_digest(
            password, self._password
        )


def require_admin(request: Request) -> None:
    header = request.headers.get("authorization")
    if header is None:
        _raise_unauthorized()
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "basic" or not value:
        _raise_unauthorized()
    try:
        decoded = base64.b64decode(value).decode("utf-8")
    except (ValueError, binascii.Error, UnicodeDecodeError):
        _raise_unauthorized()
    username, sep, password = decoded.partition(":")
    if sep != ":":
        _raise_unauthorized()
    auth = request.app.state.admin_auth
    if not isinstance(auth, AdminAuth):
        raise TypeError("app.state.admin_auth is not configured")
    if not auth.verify(username, password):
        _raise_unauthorized()


def _raise_unauthorized() -> NoReturn:
    raise HTTPException(
        status_code=401,
        detail="Unauthorized",
        headers={"WWW-Authenticate": "Basic"},
    )
