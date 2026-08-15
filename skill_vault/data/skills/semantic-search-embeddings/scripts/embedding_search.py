#!/usr/bin/env python3
"""Minimal semantic search with local embeddings and cosine similarity.

No external DB -- pure numpy + sentence-transformers. Demonstrates:
embed -> normalize -> cosine similarity -> top-k ranking.
"""

from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer


def main() -> None:
    # 1. Load a small, fast local embedding model (384-dim)
    model = SentenceTransformer("all-MiniLM-L6-v2")

    # 2. Documents to search over
    documents = [
        "How to configure SSH keys on Ubuntu",
        "Python list comprehensions and generator expressions",
        "Setting up PostgreSQL with Docker Compose",
        "Semantic search with vector embeddings explained",
        "Debugging memory leaks in Python applications",
        "Introduction to Kubernetes pods and services",
    ]

    # 3. Embed + normalize (cosine similarity = dot product when normalized)
    doc_embeddings = model.encode(documents, normalize_embeddings=True)

    # 4. Search function
    def search(query: str, top_k: int = 3) -> list[tuple[str, float]]:
        q = model.encode([query], normalize_embeddings=True)[0]
        scores = np.dot(doc_embeddings, q)  # cosine similarity (normalized)
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(documents[i], round(float(scores[i]), 4)) for i in top_indices]

    # 5. Demo
    queries = [
        "search by meaning",
        "containers and orchestration",
        "Python performance problems",
        "database setup",
    ]
    for q in queries:
        print(f"\nQuery: {q}")
        for doc, score in search(q):
            print(f"  [{score:.4f}] {doc}")


if __name__ == "__main__":
    main()
