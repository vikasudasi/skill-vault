## Embedding Model Quick Reference

### Local models (no API key, private)
| Model | Dims | Max Tokens | Use Case |
|-------|------|-----------|----------|
| all-MiniLM-L6-v2 | 384 | 256 | General; fast, small |
| bge-small-en-v1.5 | 384 | 512 | Better quality than MiniLM |
| bge-large-en-v1.5 | 1024 | 512 | Best local quality |
| all-mpnet-base-v2 | 768 | 384 | Good balance |

### API models (higher quality, needs key + network)
| Provider | Model | Dims | Max Tokens |
|----------|-------|------|-----------|
| OpenAI | text-embedding-3-small | 1536 | 8191 |
| OpenAI | text-embedding-3-large | 3072 | 8191 |
| Cohere | embed-english-v3 | 1024 | 512 |

### Embedding tips
- Embed **metadata** (title, description, tags), not full body text
- Normalize vectors for cosine similarity
- Never switch embedding models without a full re-index
- For multilingual content, use a multilingual model (paraphrase-multilingual-*)

### Progressive disclosure pattern
```
Search: embed(query) -> top-k IDs + scores
Display: fetch full content by ID only for shown results
```
This keeps the index small and fast; full text lives in a separate store.