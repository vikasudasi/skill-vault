"""Registry service — the orchestration core behind the MCP tool surface.

Wires the data model + semantic search + auth + trust layer together so the MCP
tools (``tools.py``) stay thin. Every method enforces auth scope (global visible
to all; personal only to the owning agent) and applies content-integrity /
trust-policy checks on the read path.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from skill_vault.auth import AgentContext, AuthService
from skill_vault.db import locked
from skill_vault.errors import (
    AuthenticationError,
    ForbiddenError,
    InvalidSkillError,
    NotFoundError,
)
from skill_vault.models import DeleteResult, PublishResult, SkillCard, SkillDetail, SkillInput
from skill_vault.search import SearchService
from skill_vault.trust import TrustService, canonical_payload, content_hash

_TIER_RANK = {"verified": 3, "user": 2, "public": 1}


def tier_rank(tier: str) -> int:
    return _TIER_RANK.get(tier, 0)


class RegistryService:
    """Application service exposing registry operations to the MCP tools."""

    def __init__(
        self,
        db: Any,
        *,
        auth: AuthService,
        search: SearchService,
        trust: TrustService,
    ) -> None:
        self._db = db
        self._auth = auth
        self._search = search
        self._trust = trust

    # -- auth ---------------------------------------------------------------

    def _ctx(self, agent_key: str | None) -> AgentContext:
        if agent_key is None:
            return AgentContext(agent_id=None, key_id=None, scope="guest")
        return self._auth.resolve(agent_key)

    def _require_auth(self, agent_key: str | None) -> AgentContext:
        ctx = self._ctx(agent_key)
        if not ctx.is_authenticated:
            raise AuthenticationError("an agent API key is required for this operation")
        return ctx

    def _as_agent(self, agent_id: str) -> AgentContext:
        return AgentContext(agent_id=agent_id, key_id=None, scope="authenticated")

    # -- search -------------------------------------------------------------

    def search(
        self,
        query: str,
        scope: str = "global",
        limit: int = 10,
        min_trust: str | None = None,
        agent_key: str | None = None,
    ) -> list[SkillCard]:
        ctx = self._ctx(agent_key)
        if scope == "personal":
            self._require_auth(agent_key)
        matches = self._search.search(
            query=query, scope=scope, owner_agent_id=ctx.agent_id, top_k=limit
        )
        cards: list[SkillCard] = []
        for version_id, score in matches:
            row = self._load_version_row(version_id)
            if row is None:
                continue
            tier = self._trust.resolve_tier(version_id)
            if min_trust is not None and tier_rank(tier) < tier_rank(min_trust):
                continue
            cards.append(
                SkillCard(
                    id=row["skill_id"],
                    name=row["name"],
                    description=row["description"],
                    tags=_as_list(row["tags"]),
                    trust=tier,
                    score=round(float(score), 4),
                    version=int(row["version"]),
                )
            )
        return cards

    # -- get ----------------------------------------------------------------

    def get(
        self, identifier: str, version: int | None = None, agent_key: str | None = None
    ) -> SkillDetail:
        return self._get(self._ctx(agent_key), identifier, version)

    def admin_get(self, agent_id: str, identifier: str, version: int | None = None) -> SkillDetail:
        return self._get(self._as_agent(agent_id), identifier, version)

    def _get(self, ctx: AgentContext, identifier: str, version: int | None = None) -> SkillDetail:
        row = self._resolve_version(identifier, version)
        if row is None:
            raise NotFoundError(f"no skill or version matches {identifier!r}")
        self._authorize_read(row, ctx)
        payload = self._payload_for(row)
        self._trust.ensure_integrity(row["version_id"], payload)
        tier = self._trust.resolve_tier(row["version_id"])
        sig = self._trust.verify_signature(row["version_id"], payload)
        return SkillDetail(
            id=row["skill_id"],
            name=row["name"],
            description=row["description"],
            body=row["body"],
            version=int(row["version"]),
            tags=_as_list(row["tags"]),
            trust=tier,
            content_hash=row["content_hash"],
            verified=bool(sig["verified"]),
            owner=row["owner_agent_id"],
        )

    # -- publish / update ---------------------------------------------------

    def publish(self, skill: SkillInput, visibility: str, agent_key: str | None) -> PublishResult:
        return self._publish(self._require_auth(agent_key), skill, visibility)

    def admin_publish(self, agent_id: str, skill: SkillInput, visibility: str) -> PublishResult:
        return self._publish(self._as_agent(agent_id), skill, visibility)

    def _publish(self, ctx: AgentContext, skill: SkillInput, visibility: str) -> PublishResult:
        with locked():
            if visibility not in ("global", "personal"):
                raise InvalidSkillError(
                    f"visibility must be 'global' or 'personal', got {visibility!r}"
                )
            if not skill.name.strip():
                raise InvalidSkillError("skill name is required")
            if not skill.body.strip():
                raise InvalidSkillError("skill body is required")

            payload = _build_payload(skill)
            digest = content_hash(payload)
            skill_id = str(uuid.uuid4())
            version_id = str(uuid.uuid4())
            now = _utc_now()

            self._db.execute(
                "INSERT INTO skills(id, name, owner_agent_id, visibility, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (skill_id, skill.name.strip(), ctx.agent_id, visibility, now, now),
            )
            self._insert_version(skill_id, version_id, 1, digest, skill, now)
            self._db.execute(
                "UPDATE skills SET current_version_id = ? WHERE id = ?", (version_id, skill_id)
            )
            self._record_trust(version_id, ctx.agent_id, visibility)
            self._search.index_version(version_id)
            self._db.commit()
            return PublishResult(ok=True, id=skill_id, version=1, content_hash=digest)

    def update(self, identifier: str, skill: SkillInput, agent_key: str | None) -> PublishResult:
        return self._update(self._require_auth(agent_key), identifier, skill)

    def admin_update(self, agent_id: str, identifier: str, skill: SkillInput) -> PublishResult:
        return self._update(self._as_agent(agent_id), identifier, skill)

    def _update(self, ctx: AgentContext, identifier: str, skill: SkillInput) -> PublishResult:
        with locked():
            if not skill.name.strip() or not skill.body.strip():
                raise InvalidSkillError("name and body are required")
            skill_row = self._load_skill(identifier)
            if skill_row is None:
                raise NotFoundError(f"no skill matches {identifier!r}")
            if skill_row["owner_agent_id"] != ctx.agent_id:
                raise ForbiddenError("only the owning agent may update this skill")

            next_version = int(
                self._db.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 AS nv FROM skill_versions WHERE skill_id = ?",
                    (skill_row["id"],),
                ).fetchone()["nv"]
            )
            payload = _build_payload(skill)
            digest = content_hash(payload)
            version_id = str(uuid.uuid4())
            now = _utc_now()
            self._insert_version(skill_row["id"], version_id, next_version, digest, skill, now)
            self._db.execute(
                "UPDATE skills SET current_version_id = ?, name = ?, updated_at = ? WHERE id = ?",
                (version_id, skill.name.strip(), now, skill_row["id"]),
            )
            self._record_trust(version_id, ctx.agent_id, skill_row["visibility"])
            self._search.index_version(version_id)
            if skill_row["current_version_id"]:
                self._search.remove_version(skill_row["current_version_id"])
            self._db.commit()
            return PublishResult(ok=True, id=skill_row["id"], version=next_version, content_hash=digest)

    # -- delete -------------------------------------------------------------

    def delete(self, identifier: str, agent_key: str | None) -> DeleteResult:
        return self._delete(self._require_auth(agent_key), identifier)

    def admin_delete(self, agent_id: str, identifier: str) -> DeleteResult:
        return self._delete(self._as_agent(agent_id), identifier)

    def _delete(self, ctx: AgentContext, identifier: str) -> DeleteResult:
        with locked():
            skill_row = self._load_skill(identifier)
            if skill_row is None:
                raise NotFoundError(f"no skill matches {identifier!r}")
            if skill_row["owner_agent_id"] != ctx.agent_id:
                raise ForbiddenError("only the owning agent may delete this skill")

            version_ids = [
                r["id"]
                for r in self._db.execute(
                    "SELECT id FROM skill_versions WHERE skill_id = ?", (skill_row["id"],)
                ).fetchall()
            ]
            for vid in version_ids:
                self._search.remove_version(vid)
                self._db.execute("DELETE FROM trust WHERE skill_version_id = ?", (vid,))
            # Break the FK back-reference (current_version_id) before deleting versions.
            self._db.execute(
                "UPDATE skills SET current_version_id = NULL WHERE id = ?",
                (skill_row["id"],),
            )
            self._db.execute("DELETE FROM skill_versions WHERE skill_id = ?", (skill_row["id"],))
            self._db.execute("DELETE FROM skills WHERE id = ?", (skill_row["id"],))
            self._db.commit()
            return DeleteResult(ok=True, id=skill_row["id"], deleted=True)

    # -- listing ------------------------------------------------------------

    def list_my(self, agent_key: str | None) -> list[SkillCard]:
        ctx = self._require_auth(agent_key)
        return self._list_my(ctx.agent_id)

    def admin_list_my(self, agent_id: str) -> list[SkillCard]:
        return self._list_my(agent_id)

    def _list_my(self, agent_id: str | None) -> list[SkillCard]:
        rows = self._db.execute(
            "SELECT s.id AS skill_id, v.id AS version_id, v.name, v.description, v.tags, "
            "v.version FROM skills s JOIN skill_versions v ON v.id = s.current_version_id "
            "WHERE s.owner_agent_id = ? ORDER BY s.updated_at DESC",
            (agent_id,),
        ).fetchall()
        return [self._card_from_row(r) for r in rows]

    def list_global(self, limit: int = 20, offset: int = 0) -> list[SkillCard]:
        rows = self._db.execute(
            "SELECT s.id AS skill_id, v.id AS version_id, v.name, v.description, v.tags, "
            "v.version FROM skills s JOIN skill_versions v ON v.id = s.current_version_id "
            "WHERE s.visibility = 'global' ORDER BY s.updated_at DESC LIMIT ? OFFSET ?",
            (max(limit, 1), max(offset, 0)),
        ).fetchall()
        return [self._card_from_row(r) for r in rows]

    # -- internal helpers ---------------------------------------------------

    def _authorize_read(self, row: Any, ctx: AgentContext) -> None:
        if row["visibility"] == "personal":
            if ctx.agent_id is None:
                raise AuthenticationError("authentication required for personal skills")
            if row["owner_agent_id"] != ctx.agent_id:
                raise ForbiddenError("this personal skill belongs to another agent")

    def _card_from_row(self, row: Any) -> SkillCard:
        return SkillCard(
            id=row["skill_id"],
            name=row["name"],
            description=row["description"],
            tags=_as_list(row["tags"]),
            trust=self._trust.resolve_tier(row["version_id"]),
            score=0.0,
            version=int(row["version"]),
        )

    def _record_trust(self, version_id: str, owner_agent_id: str | None, visibility: str) -> None:
        tier = self._trust.compute_tier(
            owner_agent_id=owner_agent_id,
            signature=None,
            public_key=None,
            visibility=visibility,
        )
        self._trust.record(version_id, tier)

    def _insert_version(
        self, skill_id: str, version_id: str, version: int, digest: str, skill: SkillInput, now: str
    ) -> None:
        self._db.execute(
            "INSERT INTO skill_versions(id, skill_id, version, content_hash, name, description, "
            "tags, triggers, meta_json, body, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                version_id,
                skill_id,
                version,
                digest,
                skill.name.strip(),
                skill.description.strip(),
                json.dumps(skill.tags),
                json.dumps(skill.triggers),
                json.dumps(skill.meta),
                skill.body,
                now,
            ),
        )

    def _load_skill(self, identifier: str) -> Any:
        return self._db.execute("SELECT * FROM skills WHERE id = ?", (identifier,)).fetchone()

    def _load_version_row(self, version_id: str) -> Any:
        row = self._db.execute(
            "SELECT v.id AS version_id, v.skill_id, v.version, v.content_hash, v.name, "
            "v.description, v.tags, v.triggers, v.meta_json, v.body, "
            "s.visibility, s.owner_agent_id "
            "FROM skill_versions v JOIN skills s ON s.id = v.skill_id WHERE v.id = ?",
            (version_id,),
        ).fetchone()
        return row if row is not None else None

    def _resolve_version(self, identifier: str, version: int | None) -> Any:
        """Resolve ``identifier`` as a skill id (current or requested version) or version_id."""
        skill = self._load_skill(identifier)
        if skill is not None:
            if version is None:
                return (
                    self._load_version_row(skill["current_version_id"])
                    if skill["current_version_id"]
                    else None
                )
            row = self._db.execute(
                "SELECT v.id AS version_id FROM skill_versions v WHERE v.skill_id = ? "
                "AND v.version = ?",
                (identifier, version),
            ).fetchone()
            return self._load_version_row(row["version_id"]) if row else None
        return self._load_version_row(identifier)

    def _payload_for(self, row: Any) -> bytes:
        return canonical_payload(
            name=row["name"],
            description=row["description"],
            tags=_as_list(row["tags"]),
            triggers=_as_list(row["triggers"]),
            meta_json=_as_dict(row["meta_json"]),
            body=row["body"],
        )


def _build_payload(skill: SkillInput) -> bytes:
    return canonical_payload(
        name=skill.name.strip(),
        description=skill.description.strip(),
        tags=skill.tags,
        triggers=skill.triggers,
        meta_json=skill.meta,
        body=skill.body,
    )


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    try:
        parsed = json.loads(value)
        return [str(v) for v in parsed] if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def _utc_now() -> str:
    import datetime

    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
