---
name: agent-tool-use
description: Design AI agents that call tools reliably — schema design, error handling, multi-step planning, and grounding.
tags: [agent, tool-use, function-calling, llm, ai, orchestration]
triggers: [agent, tool use, function calling, tool call, multi-step]
complexity: high
time_estimate: 60-120 min
prerequisites: [an LLM with function-calling, python or js]
source: Skill Vault curated library
verify: true
---

# Designing Agents that Use Tools

Use when an LLM should take actions via tools rather than just generate text.

## Core loop

```
user -> plan -> [tool call] -> observe -> next step -> ... -> answer
```

Maintain an explicit state of what the agent has done and what it knows; don't
let it freewheel.

## Tool schema design

- **Narrow + typed** tools; the schema is the contract the model reads.
- One action per tool; compose complex behavior from small tools.
- Return structured, machine-readable results the agent can act on
  (Skill Vault returns lightweight `SkillCard`s, then a fetch tool for the body).

## Error handling

Tools fail. Surface structured errors (`{"error": "...", "code": "..."}`) so the
agent can react, retry, or report — never let a raised exception end the whole
turn without a path forward. Add retry limits to prevent infinite loops.

## Grounding

The agent's tool results are its ground truth — never let it assert a result it
didn't observe. When a skill/registry returns content, have it verify integrity
before trusting (Skill Vault's `verify_skill` + content hashes).

## Pitfalls

- Broad "do everything" tools encourage sloppy calls — split them.
- Guard against loops: cap tool calls per turn, require progress each step.
- Validate tool arguments before execution, not just after.
