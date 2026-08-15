#!/usr/bin/env python3
"""Minimal end-to-end RAG pipeline: chunk -> embed -> index -> retrieve -> generate.

Uses sentence-transformers for local embeddings and sqlite-vec for vector storage.
Self-contained; no API keys needed.
"""

from __future__ import annotations

import sqlite3
import uuid


# --- 1. Embedding model (local, free) ---
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("Install: pip install sentence-transformers sqlite-vec")
    raise

model = SentenceTransformer("all-MiniLM-L6-v2")  # 384-dim


# --- 2. Vector store (sqlite-vec) ---
try:
    import sqlite_vec
except ImportError:
    print("Install: pip install sqlite-vec")
    raise

DB_PATH = ":memory:"


def _ensure_sqlite_vec() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def create_index(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING vec0(embedding float[384])")
    conn.execute("CREATE TABLE IF NOT EXISTS chunk_texts (id TEXT PRIMARY KEY, text TEXT)")
    conn.commit()


def insert_chunks(conn: sqlite3.Connection, texts: list[str]) -> None:
    embeddings = model.encode(texts, normalize_embeddings=True)
    for text, embedding in zip(texts, embeddings):
        chunk_id = str(uuid.uuid4())
        conn.execute("INSERT INTO chunk_texts (id, text) VALUES (?, ?)", (chunk_id, text))
        conn.execute(
            "INSERT INTO chunks (id, embedding) VALUES (?, ?)",
            (chunk_id, embedding.tobytes()),
        )
    conn.commit()


def search(conn: sqlite3.Connection, query: str, top_k: int = 3) -> list[tuple[str, float]]:
    q_embedding = model.encode([query], normalize_embeddings=True)[0]
    rows = conn.execute(
        """SELECT ct.text, vec_distance_cosine(c.embedding, ?) AS score
           FROM chunks c JOIN chunk_texts ct ON c.id = ct.id
           ORDER BY score ASC LIMIT ?""",
        (q_embedding.tobytes(), top_k),
    ).fetchall()
    return [(row[0], 1.0 - row[1]) for row in rows]  # similarity = 1 - distance


# --- 3. Demo ---


def main() -> None:
    conn = _ensure_sqlite_vec()
    create_index(conn)

    documents = [
        "Python is a high-level programming language known for readability.",
        "SQLite is a self-contained, serverless SQL database engine.",
        "RAG stands for Retrieval-Augmented Generation, combining search with LLMs.",
        "Vector embeddings map text to dense numerical vectors for similarity search.",
    ]
    insert_chunks(conn, documents)

    queries = [
        "What is RAG?",
        "Tell me about databases",
        "What language is Python?",
    ]
    for q in queries:
        results = search(conn, q, top_k=2)
        print(f"\nQuery: {q}")
        for text, score in results:
            print(f"  [{score:.4f}] {text[:80]}")

    conn.close()


if __name__ == "__main__":
    main()
