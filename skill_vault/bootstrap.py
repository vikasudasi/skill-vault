"""Dependency bootstrap — construct the full service stack from settings."""

from __future__ import annotations

import sqlite3
from typing import cast

from skill_vault.auth import AuthService
from skill_vault.config import Settings, get_settings
from skill_vault.db import ConnectionProxy, connect, connect_threadlocal, run_migrations
from skill_vault.search import Embedder, SearchService, build_store
from skill_vault.service import RegistryService
from skill_vault.trust import TrustService


class Services:
    """Holds the live service instances used by the MCP server and web app."""

    def __init__(
        self,
        db: sqlite3.Connection | ConnectionProxy,
        auth: AuthService,
        search: SearchService,
        trust: TrustService,
        registry: RegistryService,
    ) -> None:
        resolved_db = _resolve_threadlocal_db(db, auth, search, trust, registry)
        self.db = cast(sqlite3.Connection, resolved_db)
        self.auth = auth
        self.search = search
        self.trust = trust
        self.registry = registry


def _resolve_threadlocal_db(
    db: sqlite3.Connection | ConnectionProxy,
    auth: AuthService,
    search: SearchService,
    trust: TrustService,
    registry: RegistryService,
) -> sqlite3.Connection | ConnectionProxy:
    if isinstance(db, ConnectionProxy):
        return db
    db_path = _db_path(db)
    if not db_path:
        return db
    proxy = connect_threadlocal(db_path)
    proxy_as_conn = cast(sqlite3.Connection, proxy)
    auth._db = proxy_as_conn
    search._db = proxy_as_conn
    trust._db = proxy_as_conn
    registry._db = proxy
    db.close()
    return proxy


def _db_path(db: sqlite3.Connection) -> str | None:
    row = db.execute("PRAGMA database_list;").fetchone()
    if row is None:
        return None
    path = str(row[2]).strip()
    if not path or path == ":memory:":
        return None
    return path


def build_services(settings: Settings | None = None) -> Services:
    """Connect DB, run migrations, and construct auth/search/trust/registry."""
    settings = settings or get_settings()
    migration_db = connect(settings.db_path)
    run_migrations(migration_db, "migrations")
    migration_db.close()
    db = connect_threadlocal(settings.db_path)
    auth = AuthService(cast(sqlite3.Connection, db), rate_limit=settings.rate_limit_per_minute)
    store = build_store(settings.vector_backend, settings.db_path, settings.pgvector_dsn)
    embedder = Embedder(settings.embed_model)
    search = SearchService(cast(sqlite3.Connection, db), store, embedder)
    trust = TrustService(cast(sqlite3.Connection, db), allow_tiers=settings.trust_allow.split(","))
    registry = RegistryService(db, auth=auth, search=search, trust=trust)
    return Services(
        db=cast(sqlite3.Connection, db),
        auth=auth,
        search=search,
        trust=trust,
        registry=registry,
    )
