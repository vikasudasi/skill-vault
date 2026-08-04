from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(slots=True)
class Settings:
    db_path: str
    vector_backend: str
    embed_model: str
    trust_allow: str
    curator_key: str | None
    web_host: str
    web_port: int
    seed_dir: str
    pgvector_dsn: str | None
    rate_limit_per_minute: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        db_path=os.getenv("SKILL_VAULT_DB_PATH", "./skill_vault.db"),
        vector_backend=os.getenv("SKILL_VAULT_VECTOR_BACKEND", "sqlite_vec"),
        embed_model=os.getenv("SKILL_VAULT_EMBED_MODEL", "all-MiniLM-L6-v2"),
        trust_allow=os.getenv("SKILL_VAULT_TRUST_ALLOW", "verified,user"),
        curator_key=os.getenv("SKILL_VAULT_CURATOR_KEY") or None,
        web_host=os.getenv("SKILL_VAULT_WEB_HOST", "0.0.0.0"),
        web_port=int(os.getenv("SKILL_VAULT_WEB_PORT", "8000")),
        seed_dir=os.getenv("SKILL_VAULT_SEED_DIR", "./skill_vault/data/skills"),
        pgvector_dsn=os.getenv("SKILL_VAULT_PGVECTOR_DSN") or None,
        rate_limit_per_minute=int(os.getenv("SKILL_VAULT_RATE_LIMIT_PER_MINUTE", "60")),
    )
