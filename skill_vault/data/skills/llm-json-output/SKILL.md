---
name: llm-json-output
description: Get reliable structured JSON from LLMs — schema enforcement, delimiters, validation, and retry loops.
tags: [llm, json, structured-output, ai, function-calling, parsing]
triggers: [structured output, json, json mode, function calling, parse llm]
complexity: medium
time_estimate: 30-60 min
prerequisites: [an LLM API with JSON support]
source: Skill Vault curated library
---

# Reliable Structured JSON from LLMs

Use when an LLM must return machine-parseable JSON — for tool results, configs,
or data you validate downstream.

## Prefer native structured output when available

Many providers offer a JSON schema / structured-output mode that constrains
generation. If available, pass your Pydantic schema and skip manual prompt hacks.

## Fallback: prompt with a schema

```text
Return a JSON object with exactly these keys:
{"name": string, "port": int, "enabled": bool}
No other text, no markdown fences.
```

Add 1-2 examples of the exact shape you want.

## Always validate + retry

Never trust the raw string. Parse, validate against your model, and on failure
re-prompt with the error (`Invalid JSON: {e}. Please retry`). Cap retries (2-3);
if still failing, fall back to a degraded default.

## Strip markdown fences

Models often wrap JSON in ` ```json ` fences — strip them before `json.loads`.

## Pitfalls

- JSON is order-sensitive to the model's tokens, not to you: keep the schema small.
- Booleans/numbers coerce surprisingly; validate types, not just that it parses.
- Don't paste secrets or huge schemas into the prompt — it costs tokens and dilutes output.
