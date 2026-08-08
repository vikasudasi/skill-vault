---
name: semantic-search-embeddings
description: Build semantic search with embeddings — choose a model, embed metadata, store vectors, and rank by cosine similarity.
tags: [embeddings, semantic-search, vector, rag, ai, llm]
triggers: [semantic search, embeddings, vector search, similarity, cosine]
complexity: medium
time_estimate: 45-90 min
prerequisites: [python, an embedding model]
source: Skill Vault curated library
verify: true
---

# Semantic Search with Embeddings

Use when keyword search is too brittle and you want to retrieve by meaning.

## Pipeline

1. **Embed documents** → vectors.
2. **Store** in a vector index (SQLite sqlite-vec, pgvector, FAISS, Qdrant…).
3. **Query** → embed the query, compute cosine similarity, take top-k.
4. **Filter** → apply scope/trust/visibility *after* similarity.

## Embed the right text

Embed discovery **metadata** (title, description, tags, trigger phrases), not the
full body. This mirrors Skill Vault's approach: it keeps indexes small and
retrieval focused on *what it's for*, not every word. Weight: name + description
+ a few keywords is usually enough for good recall.

## Pick a model

- Local, cheap, deterministic: **all-MiniLM-L6-v2** (384-dim) — good for
  self-hosted, private searches (Skill Vault uses this, same as agent-knowledge-graph).
- Higher quality, bigger: OpenAI/Mistral embedding APIs (1536+ dims) — needs a key + network.

## Ranking

Cosine similarity is standard; normalize vectors so dot product == cosine. Round
scores for stable display (Skill Vault rounds to 4 dp).

## Pitfalls

- Embedding garbage in → garbage out: dedupe/normalize text first.
- Keep the vector dimension fixed to the model; switching models orphans old vectors.
- Store only metadata embeddings; return full content by id on demand
  (progressive disclosure) to keep the index small.
