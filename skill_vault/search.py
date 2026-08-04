from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from typing import Any


class VectorIndex(ABC):
    @abstractmethod
    def upsert(self, version_id: str, embedding: list[float]) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, version_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def query(self, embedding: list[float], top_k: int) -> list[tuple[str, float]]:
        raise NotImplementedError


class SqliteVecIndex(VectorIndex):
    def __init__(self, db_path: str) -> None:
        self._db = sqlite3.connect(db_path)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys=ON;")
        self._load_sqlite_vec()
        self._db.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS skill_embeddings
            USING vec0(embedding float[384]);
            """
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS skill_embedding_versions (
                version_id TEXT PRIMARY KEY,
                embedding_rowid INTEGER NOT NULL UNIQUE
            );
            """
        )

    def _load_sqlite_vec(self) -> None:
        import sqlite_vec

        sqlite_vec.load(self._db)

    def upsert(self, version_id: str, embedding: list[float]) -> None:
        if len(embedding) != 384:
            raise ValueError("sqlite-vec index requires 384-dimensional embeddings.")
        import sqlite_vec

        existing = self._db.execute(
            "SELECT embedding_rowid FROM skill_embedding_versions WHERE version_id = ?",
            (version_id,),
        ).fetchone()
        if existing is not None:
            self._db.execute(
                "DELETE FROM skill_embeddings WHERE rowid = ?",
                (existing["embedding_rowid"],),
            )
            self._db.execute(
                "DELETE FROM skill_embedding_versions WHERE version_id = ?",
                (version_id,),
            )

        serialized = sqlite_vec.serialize_float32(embedding)
        self._db.execute(
            "INSERT INTO skill_embeddings(embedding) VALUES (?)",
            (serialized,),
        )
        rowid = int(self._db.execute("SELECT last_insert_rowid()").fetchone()[0])
        self._db.execute(
            "INSERT INTO skill_embedding_versions(version_id, embedding_rowid) VALUES(?, ?)",
            (version_id, rowid),
        )
        self._db.commit()

    def delete(self, version_id: str) -> None:
        existing = self._db.execute(
            "SELECT embedding_rowid FROM skill_embedding_versions WHERE version_id = ?",
            (version_id,),
        ).fetchone()
        if existing is None:
            return
        self._db.execute(
            "DELETE FROM skill_embeddings WHERE rowid = ?",
            (existing["embedding_rowid"],),
        )
        self._db.execute("DELETE FROM skill_embedding_versions WHERE version_id = ?", (version_id,))
        self._db.commit()

    def query(self, embedding: list[float], top_k: int) -> list[tuple[str, float]]:
        raise NotImplementedError("Vector similarity query implementation is pending.")


class Embedder:
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
        vectors = self._get_model().encode(texts, normalize_embeddings=True)
        return [[float(value) for value in row.tolist()] for row in vectors]
