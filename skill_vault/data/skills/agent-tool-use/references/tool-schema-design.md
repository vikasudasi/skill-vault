# Tool Schema Design Reference

## Naming conventions

- **Verb-first:** `get_weather`, `list_users`, `create_order`, `delete_cache`
- **No abbreviations** agents can misinterpret: `get_usr` → `get_user`
- **One action per tool** — compose complex behavior from simple, well-named tools

## Parameter design

| Practice | Example |
|----------|---------|
| Explicit types | `"temperature": {"type": "number", "minimum": -50, "maximum": 60}` |
| Required vs optional | Mark genuinely required fields `"required": ["city"]` |
| Enums for closed sets | `"format": {"type": "string", "enum": ["json", "xml", "csv"]}` |
| Descriptive `description` field | Every parameter — the model reads these |

## Error response contract

Every tool should return a consistent error envelope:
```json
{"error": "human-readable message", "code": "INVALID_CITY", "retryable": true}
```
This allows the agent to decide: retry, ask the user, or try a different tool.

## Grounding

- Agent tool results are **ground truth** — never let the model assert a result it did not observe
- Verify tool results (hashes, signatures) before trusting, especially for registry-style systems
- Log every tool call + result for debugging and audit

## Guardrails

- Cap total tool calls per turn (prevent infinite loops)
- Require observable progress each step (no repeated identical calls)
- Validate arguments before execution, not just after
