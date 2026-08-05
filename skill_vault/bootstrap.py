"""Dependency bootstrap — construct the full service stack from settings."""

from __future__ import annotations

import sqlite3

from skill_vault.auth import AuthService
from skill_vault.config import Settings, get_settings
from skill_vault.db import connect, run_migrations
from skill_vault.search import Embedder, SearchService, build_store
from skill_vault.service import RegistryService
from skill_vault.trust import TrustService


class Services:
    """Holds the live service instances used by the MCP server and web app."""

    def __init__(
        self,
        db: sqlite3.Connection,
        auth: AuthService,
        search: SearchService,
        trust: TrustService,
        registry: RegistryService,
    ) -> None:
        self.db = db
        self.auth = auth
        self.search = search
        self.trust = trust
        self.registry = registry


def build_services(settings: Settings | None = None) -> Services:
    """Connect DB, run migrations, and construct auth/search/trust/registry."""
    settings = settings or get_settings()
    db = connect(settings.db_path)
    run_migrations(db, "migrations")
    auth = AuthService(db, rate_limit=settings.rate_limit_per_minute)
    store = build_store(settings.vector_backend, settings.db_path, settings.pgvector_dsn)
    embedder = Embedder(settings.embed_model)
    search = SearchService(db, store, embedder)
    trust = TrustService(db, allow_tiers=settings.trust_allow.split(","))
    registry = RegistryService(db, auth=auth, search=search, trust=trust)
    return Services(db=db, auth=auth, search=search, trust=trust, registry=registry)
