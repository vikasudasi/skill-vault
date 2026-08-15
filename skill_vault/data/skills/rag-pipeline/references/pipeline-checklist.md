## RAG Pipeline Checklist

### Chunking (the #1 quality lever)
- [ ] Split on semantic boundaries (headings, paragraphs), not fixed char counts
- [ ] Chunk size 200-500 words
- [ ] Overlap 10-20% to avoid boundary splits
- [ ] Attach metadata: source, section heading, page, timestamp

### Embedding
- [ ] Same model for index and query
- [ ] Normalize vectors for cosine similarity
- [ ] Model dimension fixed; switching models = full re-index

### Indexing
- [ ] Store chunk text separately from vectors (progressive disclosure)
- [ ] Index metadata fields for filtering (scope, tenant, date)
- [ ] Re-index on any model or chunking change

### Retrieval
- [ ] Top-k tuned to your context window (5-10 typical)
- [ ] Return scores; threshold low-confidence results
- [ ] Re-rank if corpus is large or recall needs improvement
- [ ] Filter by metadata before final ranking

### Generation
- [ ] System prompt: "Answer ONLY from the provided context"
- [ ] Include source citations in the prompt
- [ ] Instruct model to say "I don't know" for unsupported queries
- [ ] Keep temperature low (0-0.3) for factual Q&A

### Evaluation
- [ ] Labeled eval set: 50-200 question -> relevant-chunk pairs
- [ ] Measure recall@k and faithfulness separately
- [ ] Re-run evals on every chunking/indexing change
