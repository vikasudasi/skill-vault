"""Semantic search backend for Skill Vault.

Design (see docs/SPEC.md §6 and ADR-001):
- Local embeddings via sentence-transformers ``all-MiniLM-L6-v2`` (384-d), normalized.
- Two indexed *channels* per skill version:
    * ``meta``  — clean discovery metadata (name, description, tags, triggers)
    * ``body``  — the SKILL.md markdown body (richer, truncated)
  Keeping them separate avoids polluting the clean search space with instruction prose.
  At query time the query is embedded once and scored against both channels, combined
  with configurable weights (meta-weighted by default).
- Storage behind a ``VectorStore`` interface so the backend is swappable (sqlite-vec by
  default, optional pgvector).
- ``SearchService`` ties the vector index to the SQLite registry: it builds/embeds the
  channel texts, upserts vectors, runs ranked queries, and applies scope filtering
  (global vs same-user team vs own-personal) at query time.
"""

from __future__ import annotations

import sqlite3
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from skill_vault.models import SkillVersion

EMBED_DIM = 384
# Relative weight of the meta channel vs the body channel when combining scores.
META_WEIGHT = 0.6
BODY_WEIGHT = 0.4
# Cap on body text given to the embedder (keeps indexes small / fast).
BODY_MAX_CHARS = 2000


class Embedder:
    """Lazy-loading wrapper around a sentence-transformers model.

    All vectors are L2-normalized so cosine similarity == dot product and sqlite-vec's
    cosine ``distance`` maps to similarity as ``1 - distance``.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model: Any | None = None

    def _get_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, text: str) -> list[float]:
        vector = self._get_model().encode(text, normalize_embeddings=True)
        return [float(value) for value in vector.tolist()]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._get_model().encode(texts, normalize_embeddings=True)
        return [[float(value) for value in row.tolist()] for row in vectors]


# ---------------------------------------------------------------------------
# Text building (frontmatter vs body channels)
# ---------------------------------------------------------------------------


def build_meta_text(version: SkillVersion) -> str:
    """Concatenated discovery metadata used for the clean ``meta`` channel."""
    tags = " ".join(version.tags)
    triggers = " ".join(version.triggers)
    parts = [
        version.name,
        version.description,
        tags,
        triggers,
    ]
    return " ".join(part for part in parts if part).strip()


def build_body_text(version: SkillVersion) -> str:
    """Body text (truncated) used for the richer ``body`` channel."""
    body = version.body.strip()
    return body[:BODY_MAX_CHARS]


# ---------------------------------------------------------------------------
# Vector store interface + backends
# ---------------------------------------------------------------------------


class VectorStore(ABC):
    """Stores one vector per channel per skill version and supports ranked search."""

    def __init__(
        self, *, meta_weight: float = META_WEIGHT, body_weight: float = BODY_WEIGHT
    ) -> None:
        self._meta_weight = meta_weight
        self._body_weight = body_weight

    @abstractmethod
    def upsert(
        self,
        version_id: str,
        meta: list[float],
        body: list[float],
        *,
        visibility: str | None = None,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> None:
        """Insert or replace the meta + body vectors for ``version_id``."""

    @abstractmethod
    def delete(self, version_id: str) -> None:
        """Remove all vectors for ``version_id`` (no-op if absent)."""

    @abstractmethod
    def query(
        self,
        meta: list[float],
        body: list[float],
        top_k: int,
        *,
        filter: dict[str, str] | None = None,
    ) -> list[tuple[str, float]]:
        """Return ``(version_id, combined_similarity)`` pairs, best-first.

        ``filter`` is an optional payload filter dict of the form
        ``{"visibility": "global", "owner_agent_id": "..."}``; backends without
        native filtering ignore it.
        """

    def _combine(self, meta_sim: float | None, body_sim: float | None) -> float:
        """Weighted combine of per-channel similarities (0..1); missing channel -> 0 weight."""
        meta_sim = meta_sim if meta_sim is not None else 0.0
        body_sim = body_sim if body_sim is not None else 0.0
        return self._meta_weight * meta_sim + self._body_weight * body_sim


class SqliteVecStore(VectorStore):
    """sqlite-vec backed index (default, self-host). Two vec0 tables + a rowid map."""

    def __init__(
        self,
        db_path: str,
        *,
        meta_weight: float = META_WEIGHT,
        body_weight: float = BODY_WEIGHT,
    ) -> None:
        super().__init__(meta_weight=meta_weight, body_weight=body_weight)
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL;")
        self._db.execute("PRAGMA foreign_keys=ON;")
        self._enable_extension(self._db)
        for table in ("skill_embeddings_meta", "skill_embeddings_body"):
            self._db.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING vec0(embedding float[{EMBED_DIM}]);"
            )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS skill_embedding_map (
                version_id TEXT PRIMARY KEY,
                meta_rowid  INTEGER,
                body_rowid  INTEGER
            );
            """
        )
        self._db.commit()

    # Need the connection for sqlite_vec.load; keep a module-level helper.
    @staticmethod
    def _enable_extension(db: sqlite3.Connection) -> None:
        import sqlite_vec

        db.enable_load_extension(True)
        sqlite_vec.load(db)

    def _ensure_ext(self) -> None:
        self._enable_extension(self._db)

    def upsert(
        self,
        version_id: str,
        meta: list[float],
        body: list[float],
        *,
        visibility: str | None = None,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> None:
        if len(meta) != EMBED_DIM or (body and len(body) != EMBED_DIM):
            raise ValueError(f"sqlite-vec requires {EMBED_DIM}-dimensional vectors.")
        self._ensure_ext()
        import sqlite_vec

        row = self._db.execute(
            "SELECT meta_rowid, body_rowid FROM skill_embedding_map WHERE version_id = ?",
            (version_id,),
        ).fetchone()

        meta_rid = row["meta_rowid"] if row else None
        body_rid = row["body_rowid"] if row else None

        if meta_rid is not None:
            self._db.execute("DELETE FROM skill_embeddings_meta WHERE rowid = ?", (meta_rid,))
        if body_rid is not None:
            self._db.execute("DELETE FROM skill_embeddings_body WHERE rowid = ?", (body_rid,))

        if meta:
            self._db.execute(
                "INSERT INTO skill_embeddings_meta(embedding) VALUES (?)",
                (sqlite_vec.serialize_float32(meta),),
            )
            meta_rid = int(self._db.execute("SELECT last_insert_rowid()").fetchone()[0])
        if body:
            self._db.execute(
                "INSERT INTO skill_embeddings_body(embedding) VALUES (?)",
                (sqlite_vec.serialize_float32(body),),
            )
            body_rid = int(self._db.execute("SELECT last_insert_rowid()").fetchone()[0])

        self._db.execute(
            "INSERT INTO skill_embedding_map(version_id, meta_rowid, body_rowid) VALUES(?, ?, ?) "
            "ON CONFLICT(version_id) DO UPDATE SET meta_rowid=excluded.meta_rowid, "
            "body_rowid=excluded.body_rowid",
            (version_id, meta_rid, body_rid),
        )
        self._db.commit()

    def delete(self, version_id: str) -> None:
        self._ensure_ext()
        row = self._db.execute(
            "SELECT meta_rowid, body_rowid FROM skill_embedding_map WHERE version_id = ?",
            (version_id,),
        ).fetchone()
        if row is None:
            return
        if row["meta_rowid"] is not None:
            self._db.execute(
                "DELETE FROM skill_embeddings_meta WHERE rowid = ?", (row["meta_rowid"],)
            )
        if row["body_rowid"] is not None:
            self._db.execute(
                "DELETE FROM skill_embeddings_body WHERE rowid = ?", (row["body_rowid"],)
            )
        self._db.execute("DELETE FROM skill_embedding_map WHERE version_id = ?", (version_id,))
        self._db.commit()

    def query(
        self,
        meta: list[float],
        body: list[float],
        top_k: int,
        *,
        filter: dict[str, str] | None = None,
    ) -> list[tuple[str, float]]:
        if top_k <= 0:
            return []
        self._ensure_ext()
        import sqlite_vec

        # Pull a generous candidate pool from each channel, then combine + rank.
        pool_rows = max(top_k * 4, 10)
        scores: dict[str, dict[str, float]] = {}

        if meta:
            for row in self._db.execute(
                "SELECT rowid, distance FROM skill_embeddings_meta "
                "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (sqlite_vec.serialize_float32(meta), pool_rows),
            ):
                version_id = self._version_for_rowid("meta", row["rowid"])
                if version_id is not None:
                    scores.setdefault(version_id, {})["meta"] = max(0.0, 1.0 - row["distance"])
        if body:
            for row in self._db.execute(
                "SELECT rowid, distance FROM skill_embeddings_body "
                "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (sqlite_vec.serialize_float32(body), pool_rows),
            ):
                version_id = self._version_for_rowid("body", row["rowid"])
                if version_id is not None:
                    scores.setdefault(version_id, {})["body"] = max(0.0, 1.0 - row["distance"])

        ranked: list[tuple[str, float]] = []
        for version_id, chan in scores.items():
            combined = self._combine(chan.get("meta"), chan.get("body"))
            ranked.append((version_id, combined))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked[:top_k]

    def _version_for_rowid(self, channel: str, rowid: int) -> str | None:
        col = "meta_rowid" if channel == "meta" else "body_rowid"
        row = self._db.execute(
            f"SELECT version_id FROM skill_embedding_map WHERE {col} = ?", (rowid,)
        ).fetchone()
        return row["version_id"] if row else None


class PgVectorStore(VectorStore):
    """Optional pgvector adapter (same interface; requires psycopg + pgvector extension).

    Not exercised by the hermetic unit tests (which target sqlite-vec); this is the
    documented scale-out/team path per ADR-001.
    """

    def __init__(
        self,
        dsn: str,
        *,
        meta_weight: float = META_WEIGHT,
        body_weight: float = BODY_WEIGHT,
    ) -> None:
        super().__init__(meta_weight=meta_weight, body_weight=body_weight)
        self._dsn = dsn
        self._conn: Any | None = None

    def _connect(self) -> Any:
        if self._conn is None:
            import psycopg

            self._conn = psycopg.connect(self._dsn)
            self._conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS skill_vectors ("
                " version_id TEXT PRIMARY KEY, meta vector(384), body vector(384));"
            )
            self._conn.commit()
        return self._conn

    def upsert(
        self,
        version_id: str,
        meta: list[float],
        body: list[float],
        *,
        visibility: str | None = None,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT INTO skill_vectors(version_id, meta, body) VALUES(%s, %s, %s) "
            "ON CONFLICT(version_id) DO UPDATE SET meta=EXCLUDED.meta, body=EXCLUDED.body",
            (version_id, meta, body),
        )
        conn.commit()

    def delete(self, version_id: str) -> None:
        conn = self._connect()
        conn.execute("DELETE FROM skill_vectors WHERE version_id = %s", (version_id,))
        conn.commit()

    def query(
        self,
        meta: list[float],
        body: list[float],
        top_k: int,
        *,
        filter: dict[str, str] | None = None,
    ) -> list[tuple[str, float]]:
        if top_k <= 0:
            return []
        conn = self._connect()
        # Cosine distance in pgvector is 1 - cosine_similarity.
        rows = conn.execute(
            "SELECT version_id, "
            "  (1 - (meta <=> %s::vector)) * %s + "
            "  (1 - (body <=> %s::vector)) * %s AS score "
            "FROM skill_vectors ORDER BY score DESC LIMIT %s",
            (meta, self._meta_weight, body, self._body_weight, top_k),
        ).fetchall()
        return [(row[0], float(row[1])) for row in rows]


class QdrantVectorStore(VectorStore):
    """Qdrant-backed vector index (local embedded or remote server).

    Two collections (``skill_embeddings_meta`` / ``skill_embeddings_body``), one
    point per channel per skill version. Every point carries a payload with
    ``version_id``/``visibility``/``owner_agent_id``/``owner_user_id`` so queries
    can apply scope filters natively inside Qdrant instead of only post-filtering.
    """

    META_COLLECTION = "skill_embeddings_meta"
    BODY_COLLECTION = "skill_embeddings_body"
    # Namespace for deterministic point ids when ``version_id`` isn't a UUID.
    _NAMESPACE = uuid.UUID("6f8f5771-5065-4b3e-9c5e-9f0f5f7a3d1a")

    def __init__(
        self,
        *,
        url: str | None = None,
        path: str | None = None,
        meta_weight: float = META_WEIGHT,
        body_weight: float = BODY_WEIGHT,
    ) -> None:
        super().__init__(meta_weight=meta_weight, body_weight=body_weight)
        from qdrant_client import QdrantClient
        from qdrant_client.http.models import Distance, VectorParams

        self._client: Any = QdrantClient(url=url) if url else QdrantClient(path=path or ":memory:")
        for name in (self.META_COLLECTION, self.BODY_COLLECTION):
            if not self._client.collection_exists(name):
                self._client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
                )

    @staticmethod
    def _point_id(version_id: str) -> uuid.UUID:
        try:
            return uuid.UUID(version_id)
        except (ValueError, AttributeError, TypeError):
            return uuid.uuid5(QdrantVectorStore._NAMESPACE, version_id)

    @staticmethod
    def _translate_filter(filter_dict: dict[str, str] | None) -> Any:
        if not filter_dict:
            return None
        from qdrant_client.http.models import FieldCondition, Filter, MatchValue

        return Filter(
            must=[
                FieldCondition(key=key, match=MatchValue(value=value))
                for key, value in filter_dict.items()
            ]
        )

    def upsert(
        self,
        version_id: str,
        meta: list[float],
        body: list[float],
        *,
        visibility: str | None = None,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> None:
        pid = self._point_id(version_id)
        payload = {
            "version_id": version_id,
            "visibility": visibility,
            "owner_agent_id": owner_agent_id,
            "owner_user_id": owner_user_id,
        }
        if meta:
            self._upsert_channel(self.META_COLLECTION, pid, meta, payload)
        if body:
            self._upsert_channel(self.BODY_COLLECTION, pid, body, payload)

    def _upsert_channel(
        self, collection: str, pid: uuid.UUID, vector: list[float], payload: dict[str, Any]
    ) -> None:
        from qdrant_client.http.models import PointStruct

        if len(vector) != EMBED_DIM:
            raise ValueError(f"qdrant requires {EMBED_DIM}-dimensional vectors.")
        self._client.upsert(
            collection_name=collection,
            points=[PointStruct(id=pid, vector=vector, payload=payload)],
        )

    def delete(self, version_id: str) -> None:
        pid = self._point_id(version_id)
        for name in (self.META_COLLECTION, self.BODY_COLLECTION):
            self._client.delete(collection_name=name, points_selector=[pid])

    def query(
        self,
        meta: list[float],
        body: list[float],
        top_k: int,
        *,
        filter: dict[str, str] | None = None,
    ) -> list[tuple[str, float]]:
        if top_k <= 0:
            return []
        qdrant_filter = self._translate_filter(filter)
        pool = max(top_k * 4, 10)
        scores: dict[str, dict[str, float]] = {}
        if meta:
            self._collect(self.META_COLLECTION, meta, qdrant_filter, pool, scores, "meta")
        if body:
            self._collect(self.BODY_COLLECTION, body, qdrant_filter, pool, scores, "body")
        ranked = [
            (vid, self._combine(chan.get("meta"), chan.get("body"))) for vid, chan in scores.items()
        ]
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked[:top_k]

    def _collect(
        self,
        collection: str,
        vector: list[float],
        qdrant_filter: Any,
        limit: int,
        scores: dict[str, dict[str, float]],
        channel: str,
    ) -> None:
        response = self._client.query_points(
            collection_name=collection,
            query=vector,
            query_filter=qdrant_filter,
            limit=limit,
        )
        for point in response.points:
            version_id = point.payload.get("version_id")
            if version_id is None:
                continue
            scores.setdefault(str(version_id), {})[channel] = max(0.0, float(point.score))


def build_store(
    backend: str,
    db_path: str,
    pgvector_dsn: str | None = None,
    *,
    qdrant_url: str | None = None,
    qdrant_path: str | None = None,
) -> VectorStore:
    """Factory selecting the vector backend from config (swappable per ADR-001)."""
    if backend == "pgvector":
        if not pgvector_dsn:
            raise ValueError("pgvector backend requires SKILL_VAULT_PGVECTOR_DSN.")
        return PgVectorStore(pgvector_dsn)
    if backend == "qdrant":
        return QdrantVectorStore(url=qdrant_url, path=qdrant_path)
    return SqliteVecStore(db_path)


# ---------------------------------------------------------------------------
# Search service: ties the vector store to the SQLite registry + scope filtering
# ---------------------------------------------------------------------------


class SearchService:
    """Ranks skill versions via the vector store and applies scope/visibility filters.

    ``search`` returns ``(version_id, combined_score)`` pairs; the MCP tool layer joins
    those to full ``SkillCard`` objects. Cross-agent private skills are never returned.
    """

    def __init__(
        self,
        db: sqlite3.Connection,
        store: VectorStore,
        embedder: Embedder | None = None,
    ) -> None:
        self._db = db
        self._store = store
        self._embedder = embedder or Embedder()

    # -- indexing -----------------------------------------------------------

    def index_version(self, version_id: str) -> None:
        """Embed + upsert a single skill version (both channels)."""
        version = self._load_version(version_id)
        if version is None:
            raise KeyError(f"no skill version with id {version_id!r}")
        meta_vec = self._embedder.embed(build_meta_text(version))
        body_vec = self._embedder.embed(build_body_text(version))
        self._store.upsert(
            version_id,
            meta_vec,
            body_vec,
            visibility=self._visibility(version_id),
            owner_agent_id=self._owner(version_id),
            owner_user_id=self._owner_user_id(version_id),
        )

    def reindex_all(self) -> int:
        """(Re)embed every skill version in the registry. Idempotent & resumable."""
        version_ids = [
            row["id"]
            for row in self._db.execute("SELECT id FROM skill_versions ORDER BY id").fetchall()
        ]
        if not version_ids:
            return 0
        versions: list[SkillVersion] = []
        for vid in version_ids:
            loaded = self._load_version(vid)
            if loaded is not None:
                versions.append(loaded)
        metas = [build_meta_text(v) for v in versions]
        bodies = [build_body_text(v) for v in versions]
        meta_vecs = self._embedder.embed_batch(metas)
        body_vecs = self._embedder.embed_batch(bodies)
        for version, meta_vec, body_vec in zip(versions, meta_vecs, body_vecs, strict=True):
            self._store.upsert(
                version.id,
                meta_vec,
                body_vec,
                visibility=self._visibility(version.id),
                owner_agent_id=self._owner(version.id),
                owner_user_id=self._owner_user_id(version.id),
            )
        return len(versions)

    def remove_version(self, version_id: str) -> None:
        self._store.delete(version_id)

    # -- search -------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        scope: str = "global",
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """Return ranked ``(version_id, score)`` for ``query`` within ``scope``.

        Scope semantics (mirrors SPEC §5):
        - ``global``   -> only curated global skills (no owner required)
        - ``personal`` -> only the ``owner_agent_id``'s private vault (owner required)
        - ``team``     -> global + same-user team skills (owner user required)
        - ``all``      -> union of global + owner's private + same-user team
        """
        query = (query or "").strip()
        if not query or top_k <= 0:
            return []
        if owner_user_id is None and owner_agent_id is not None:
            owner_user_id = self._agent_owner_user_id(owner_agent_id)
        meta_vec = self._embedder.embed(query)
        body_vec = self._embedder.embed(query)  # same query, scored on both channels
        scope_filter = self._scope_filter(scope, owner_agent_id, owner_user_id)
        candidates = self._store.query(
            meta_vec, body_vec, top_k=max(top_k * 4, 40), filter=scope_filter
        )

        allowed = self._scope_predicate(scope, owner_agent_id, owner_user_id)
        results: list[tuple[str, float]] = []
        for version_id, score in candidates:
            visibility = self._visibility(version_id)
            if visibility is None:
                continue
            if allowed(visibility, version_id):
                results.append((version_id, score))
            if len(results) >= top_k:
                break
        return results

    # -- helpers ------------------------------------------------------------

    def _scope_predicate(
        self, scope: str, owner_agent_id: str | None, owner_user_id: str | None
    ) -> Callable[[str, str], bool]:
        def is_global(_vis: str, _vid: str) -> bool:
            return _vis == "global"

        def is_personal(vis: str, vid: str) -> bool:
            if vis != "personal" or owner_agent_id is None:
                return False
            return self._owner(vid) == owner_agent_id

        def is_own(vis: str, vid: str) -> bool:
            if vis == "global":
                return True
            if vis == "personal":
                return self._owner(vid) == owner_agent_id
            if vis == "team":
                if owner_user_id is None:
                    return False
                return self._owner_user_id(vid) == owner_user_id
            return False

        def is_team(vis: str, vid: str) -> bool:
            if vis == "global":
                return True
            if vis != "team" or owner_user_id is None:
                return False
            return self._owner_user_id(vid) == owner_user_id

        if scope == "personal":
            if owner_agent_id is None:
                return lambda _vis, _vid: False  # personal requires an authenticated owner
            return is_personal
        if scope == "team":
            if owner_user_id is None:
                return lambda _vis, _vid: False
            return is_team
        if scope == "all":
            if owner_agent_id is None:
                return lambda _vis, _vid: False
            return is_own
        # default: global
        return is_global

    def _scope_filter(
        self, scope: str, owner_agent_id: str | None, owner_user_id: str | None
    ) -> dict[str, str] | None:
        """Translate scope into a payload filter for backends with native filtering.

        Only scopes expressible as a pure-AND match are translated. ``team`` and
        ``all`` require OR semantics, so they return ``None`` and rely on the
        post-filter backstop (``_scope_predicate``).
        """
        if scope == "global":
            return {"visibility": "global"}
        if scope == "personal":
            if owner_agent_id is None:
                return None  # post-filter already yields nothing
            return {"visibility": "personal", "owner_agent_id": owner_agent_id}
        return None

    def _load_version(self, version_id: str) -> SkillVersion | None:
        row = self._db.execute(
            "SELECT * FROM skill_versions WHERE id = ?", (version_id,)
        ).fetchone()
        if row is None:
            return None
        return SkillVersion(
            id=row["id"],
            skill_id=row["skill_id"],
            version=row["version"],
            content_hash=row["content_hash"],
            name=row["name"],
            description=row["description"],
            tags=_json_list(row["tags"]),
            triggers=_json_list(row["triggers"]),
            meta_json=_json_dict(row["meta_json"]),
            body=row["body"],
            created_at=row["created_at"],
        )

    def _visibility(self, version_id: str) -> str | None:
        row = self._db.execute(
            "SELECT s.visibility FROM skill_versions v "
            "JOIN skills s ON s.id = v.skill_id WHERE v.id = ?",
            (version_id,),
        ).fetchone()
        return row["visibility"] if row else None

    def _owner(self, version_id: str) -> str | None:
        row = self._db.execute(
            "SELECT s.owner_agent_id FROM skill_versions v "
            "JOIN skills s ON s.id = v.skill_id WHERE v.id = ?",
            (version_id,),
        ).fetchone()
        return row["owner_agent_id"] if row else None

    def _owner_user_id(self, version_id: str) -> str | None:
        row = self._db.execute(
            "SELECT a.owner_user_id FROM skill_versions v "
            "JOIN skills s ON s.id = v.skill_id "
            "JOIN agents a ON a.id = s.owner_agent_id "
            "WHERE v.id = ?",
            (version_id,),
        ).fetchone()
        return row["owner_user_id"] if row else None

    def _agent_owner_user_id(self, owner_agent_id: str) -> str | None:
        row = self._db.execute(
            "SELECT owner_user_id FROM agents WHERE id = ?",
            (owner_agent_id,),
        ).fetchone()
        return row["owner_user_id"] if row else None


# ---------------------------------------------------------------------------
# Small JSON helpers (kept local to avoid a pandas/numpy dependency)
# ---------------------------------------------------------------------------


def _json_list(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    import json

    try:
        value = json.loads(raw)
        return [str(x) for x in value] if isinstance(value, list) else []
    except (ValueError, TypeError):
        return []


def _json_dict(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    import json

    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}
