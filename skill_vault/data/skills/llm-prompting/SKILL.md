---
name: llm-prompting
description: Write effective LLM prompts — structure, role framing, few-shot examples, constraints, and evaluation.
tags: [llm, prompting, ai, prompt-engineering, agents]
triggers: [prompt, prompting, llm, few-shot, system prompt]
complexity: low
time_estimate: 20-40 min
prerequisites: [an LLM API or chat tool]
source: Skill Vault curated library
verify: true
---

# Effective LLM Prompting

Use when getting an LLM to produce reliable, structured output rather than
free-form prose.

## Structure a good prompt

1. **Role** — "You are a senior Python reviewer."
2. **Task** — one clear imperative sentence.
3. **Input** — the data the model operates on.
4. **Output format** — exact schema, delimiters, or constraints.
5. **Few-shot examples** (2-3) of ideal in/out pairs.

## Prefer constraints over "be careful"

Vague warnings ("be careful", "make sure") rarely change behavior. Concrete
constraints do:

- "Return valid JSON with exactly these keys."
- "If you don't know, respond with `UNKNOWN`."
- "Do not invent API endpoints or file paths; only reuse ones in the input."

## System vs user

Put durable instructions (role, format, rules) in the **system** prompt; put the
per-request task + data in the **user** message. This keeps the instruction set
stable and cheap to cache.

## Evaluate, don't assume

Test prompts against a fixed set of inputs and count correctness — not vibes.
Tweak one variable at a time.

## Pitfalls

- Length bias: requests embedded with many instructions get model attention
  diluted; keep instructions crisp.
- Never trust the model for facts it can't know — chain-of-thought helps but
  ground truth comes from your tools/retrieval, not the prompt.
