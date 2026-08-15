# Schema Validation & Repair Patterns

## Provider support for structured output

| Provider | Feature | How to use |
|----------|---------|------------|
| OpenAI | `response_format` with JSON Schema | `response_format={"type": "json_schema", "json_schema": {...}}` |
| Anthropic | Tool use / structured outputs | Constrained tool calling |
| Gemini | Controlled generation | `response_schema` parameter |
| Ollama | JSON mode | `format: json` + schema in prompt |

## Validation checklist

1. **Parse** — `json.loads()` catches syntax errors
2. **Type-check** — Pydantic / jsonschema validates types (`int` vs `"3"`)
3. **Range-check** — numbers within bounds, strings within length
4. **Enum-check** — values are in allowed set
5. **Required-check** — all mandatory keys present
6. **Unknown field policy** — reject extras or silently drop

## Repair strategies (from simplest to most involved)

1. **Strip markdown fences** — `re.sub(r'```.*?\n?', '', text)`
2. **Fix trailing commas** — `re.sub(r',\s*}', '}', text)`, same for `]`
3. **Unescape quotes** — handle `\\"` inside strings
4. **Truncate to last valid `}`** — find balanced braces
5. **Re-prompt with error** — send the raw output + specific error back to the LLM

## Pydantic coercion caveats

Pydantic v2 by default coerces types (e.g., `"8080"` → `8080`). For strict validation:
```python
from pydantic import StrictInt, StrictStr


class Config(BaseModel):
    port: StrictInt  # rejects "8080"
    name: StrictStr
```