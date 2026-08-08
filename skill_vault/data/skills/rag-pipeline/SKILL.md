---
name: rag-pipeline
description: Build a retrieval-augmented generation pipeline — chunking, indexing, retrieval, and grounded answer synthesis.
tags: [rag, retrieval, llm, embeddings, ai, pipeline]
triggers: [rag, retrieval augmented, grounding, context injection, document qa]
complexity: medium
time_estimate: 60-120 min
prerequisites: [python, an embedding model, an LLM API]
source: Skill Vault curated library
verify: true
---

# RAG: Retrieval-Augmented Generation

Use when an LLM should answer from your documents instead of its memorized
knowledge.

## Pipeline

```
documents -> chunk -> embed -> index
                                  |
query -> embed -> retrieve top-k -> prompt(generated) -> LLM -> grounded answer
```

## Chunking

- Split on semantic boundaries (headings, paragraphs), not fixed N-char blobs.
- Keep chunks ~200-500 words — enough context, not noise.
- Overlap slightly (10-20%) so a concept spanning a boundary isn't lost.

## Retrieval

- Retrieve top-k (5-10) by similarity, then re-rank if the corpus is large.
- Filter by metadata (scope, tenant, trust) *before* final ranking (Skill Vault
  filters scopes + trust tiers after similarity).

## Grounded generation prompt

Give the LLM only the retrieved passages + the question, and instruct it to
answer from the passages, citing them — and to say it doesn't know rather than
hallucinate.

## Pitfalls

- If retrieval returns irrelevant chunks, no prompt fixes it — fix chunking/index first.
- Don't stuff the entire source into context; that's not RAG, that's context-dumping.
- Measure retrieval quality (recall@k) separately from answer quality.
