from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from skill_vault.trust import public_key_from_private_key


@dataclass(slots=True)
class Settings:
    db_path: str
    vector_backend: str
    embed_model: str
    trust_allow: str
    curator_key: str | None
    mcp_host: str
    mcp_port: int
    web_host: str
    web_port: int
    seed_dir: str
    pgvector_dsn: str | None
    rate_limit_per_minute: int
    admin_username: str
    admin_password: str
    qdrant_url: str | None = None
    qdrant_path: str | None = "./qdrant_data"

    @property
    def curator_public_key(self) -> str | None:
        """The curator's public key (base64), derived from the private signing key.

        Derived so only one secret env var (``SKILL_VAULT_CURATOR_KEY``) needs to be
        set; the public key is what gets registered in the trust policy's known-keys
        set so valid signatures resolve to tier ``verified``.
        """
        if not self.curator_key:
            return None
        return public_key_from_private_key(self.curator_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        db_path=os.getenv("SKILL_VAULT_DB_PATH", "./skill_vault.db"),
        vector_backend=os.getenv("SKILL_VAULT_VECTOR_BACKEND", "sqlite_vec"),
        embed_model=os.getenv("SKILL_VAULT_EMBED_MODEL", "all-MiniLM-L6-v2"),
        trust_allow=os.getenv("SKILL_VAULT_TRUST_ALLOW", "verified,user"),
        curator_key=os.getenv("SKILL_VAULT_CURATOR_KEY") or None,
        mcp_host=os.getenv("SKILL_VAULT_MCP_HOST", "0.0.0.0"),
        mcp_port=int(os.getenv("SKILL_VAULT_MCP_PORT", "8000")),
        web_host=os.getenv("SKILL_VAULT_WEB_HOST", "0.0.0.0"),
        web_port=int(os.getenv("SKILL_VAULT_WEB_PORT", "8080")),
        seed_dir=os.getenv("SKILL_VAULT_SEED_DIR", "./skill_vault/data/skills"),
        pgvector_dsn=os.getenv("SKILL_VAULT_PGVECTOR_DSN") or None,
        rate_limit_per_minute=int(os.getenv("SKILL_VAULT_RATE_LIMIT_PER_MINUTE", "60")),
        admin_username=os.getenv("SKILL_VAULT_ADMIN_USERNAME", "admin"),
        admin_password=_require(
            "SKILL_VAULT_ADMIN_PASSWORD",
            "Set a strong SKILL_VAULT_ADMIN_PASSWORD (e.g. in .env) before starting the Skill Vault dashboard.",
        ),
        qdrant_url=os.getenv("SKILL_VAULT_QDRANT_URL") or None,
        qdrant_path=os.getenv("SKILL_VAULT_QDRANT_PATH") or "./qdrant_data",
    )


def _require(name: str, hint: str) -> str:
    """Fail loudly on missing required secrets instead of silently using a weak default."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required env var {name!r} is not set. {hint}")
    return value
