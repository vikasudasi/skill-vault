---
name: llm-prompting
description: Write effective LLM prompts — role framing, few-shot examples, constraints, system/user placement, and a repeatable evaluation loop.
tags: [llm, prompting, ai, prompt-engineering, agents]
triggers: [prompt, prompting, llm, few-shot, system prompt]
complexity: low
time_estimate: 30-60 min
prerequisites: [an LLM API or chat tool]
source: Skill Vault curated library
verify: true
---

# Effective LLM Prompting

Use when getting an LLM to produce reliable output — structured or free-form —
rather than hoping a vague instruction happens to work. Prompts are code: they
drift, they regress, and they need tests.

Pair this with the **llm-json-output** skill when the target must be
machine-parseable JSON. Rule of thumb established there: if the provider
supports a native structured-output / JSON-schema mode, **use that first** and
treat free-form prompting as the fallback. This skill is about making the
fallback (and any free-form generation) as reliable as possible.

## The five-part skeleton

1. **Role** — one line of expertise/framing: "You are a senior Python reviewer."
2. **Task** — one clear imperative sentence stating the deliverable.
3. **Input** — the data the model operates on (small, self-contained, as ground truth).
4. **Output format** — exact schema, delimiters, or shape; state "no other text".
5. **Few-shot examples** — 2-3 ideal in/out pairs only when ambiguity exists.

### Worked example, applied end-to-end

Goal: extract {port, enabled, name} from a config blob, drift-free.

```text
[SYSTEM]
You are a config parser. Extract exactly three fields from the input into a
JSON object. Follow the schema, never invent values, never add prose.

[USER]
Input:
  service: metrics, listen: 0.0.0.0:9100, tls: off
Return exactly: {"name": string, "port": int, "enabled": bool}
Example: "grafana" -> {"name": "grafana", "port": 3000, "enabled": true}
```

Then validate: `json.loads`, type-check the three fields, and if anything is
missing or malformed re-prompt with the exact error (see llm-json-output's
retry loop). The **negative** example below ("tls: off" → `enabled: false`)
sharpens behavior more than a second positive does — show one counter-case
when the mapping is non-obvious.

## Decision table: which prompting mode when

| Mode | When | Why |
|------|------|-----|
| **Native structured output / JSON-schema** | Provider supports it and output is machine-read | Constrains generation; no parsing hacks. Always first choice for llm-json-output work. |
| **Zero-shot** | One obvious task, correct output is unambiguous | Cheapest; no example tokens; fewer chances to overfit |
| **Few-shot (2-3)** | Ambiguous mapping, custom format, or rare edge, free-form output | Shows the exact shape; cost is example tokens and overfitting risk |
| **Choose-then-run (agentic)** | Task needs search/tools first | Same skeleton, but input comes from tool results, not the prompt |

Few-shot is a remedy for ambiguity, not a default. If a clear instruction class
solves it, don't add examples that could bias the output.

## System vs user placement

- **System**: durable instructions — role, output format, guardrails, few-shot
  templates that never change.
- **User**: per-request task + data that varies every call.

Keeping the stable instruction set in `system` means the provider can cache its
prefix (cheaper + faster) and you never re-send the same rules inline. If the
format is fixed but the data changes, hold the format in system and put only
the data in user.

## Constraints beat "be careful"

Weak form (rarely changes behavior): "be careful", "make sure", "double-check".
Strong form (changes behavior): a concrete, testable restriction.

- Weak: "Return valid JSON."
- Strong: "Return a JSON object with exactly these keys; no markdown fences."

```text
BAD:  Output the answer. Be accurate and don't guess.
GOOD: If the input has no exact match, return the literal string "UNKNOWN".
      Do not invent endpoints, ports, or file paths — only reuse ones present
      in the input.
```

Each constraint should be checkable by a test, not a vibe. If you can't assert
it, it's decoration.

## Evaluate, don't assume

1. Build a **fixed eval set** — 20-50 representative inputs with expected outputs.
2. Run the whole set through the prompt, score passes automatically.
3. **Change one variable at a time** (role line, one example, one constraint) and
   re-run. Two changes at once make regressions un-attributable.
4. Keep the prompt in git; a prompt diff that flips the score is a regression.

This is the same discipline as a test suite. A prompt is "working" when a
harness says so, not when one call looked good.

## Pitfalls

- **Length bias**: models over-focus on material appearing later / near the
  answer. Put the single most important instruction last, keep it short.
- **Instruction dilution**: every extra sentence in system slightly reduces
  adherence to the ones that matter. Ruthlessly cut.
- **Token budget**: huge inputs or giant few-shot sets push the real task out of
  the model's active window. Trim input; only include what the task needs.
- **Grounding**: never trust the model for facts it can't know. Ground truth
  comes from your tools/retrieval, not the prompt — the prompt only says *how*
  to use it. See **rag-pipeline** / **semantic-search-embeddings** for retrieval.
- **Confirmable output**: Skill Vault's own search returns results the model
  consumes; keep learned prompts' output machine-parseable and make the model
  return `search_skills`-style keys rather than prose. Sibling skills use
  progressive disclosure (`search_skills` → `get_skill`) so the model retrieves a
  short card first, then the body on demand — mirror that: keep the *prompt*
  small and let retrieval supply detail.

## Checklist

- [ ] Skeleton present: role, one-line task, input, output format, (optional) few-shot.
- [ ] Provider structured output used when available; free-form is the fallback.
- [ ] Durable rules in system, per-call data in user.
- [ ] Each constraint is testable, not a "be careful".
- [ ] Fixed eval set; one variable changed per run.
- [ ] Output validated + retried on malformed (with llm-json-output).