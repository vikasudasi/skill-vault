---
name: python-dataclasses-pydantic
description: Model structured Python data with dataclasses and Pydantic — immutable value objects, validation, serialization, migration between the two.
tags: [python, dataclasses, pydantic, data-modeling, backend]
triggers: [dataclass, pydantic, model, structured data, validation]
complexity: low
time_estimate: 30-60 min
prerequisites: [python 3.11]
source: Skill Vault curated library
verify: true
---

# Data Modeling with Dataclasses + Pydantic

Use when a module carries structured records and you want type safety,
validation, or clean JSON round-tripping. The two tools overlap but solve
different problems: **dataclasses are a lightweight typing/memory tool;
Pydantic adds runtime validation + serialization at the boundary.**

## Type-safety with dataclasses

```python
from __future__ import annotations
from dataclasses import dataclass


@dataclass(slots=True)
class Point:
    x: float
    y: float
```

`@dataclass(slots=True)` reduces memory and prevents accidental attribute typos
(an unknown attribute becomes an `AttributeError`, not a silent new field).

## Validation + serialization with Pydantic (v2)

```python
from pydantic import BaseModel, Field


class SkillInput(BaseModel):
    name: str = Field(min_length=3, max_length=64)
    description: str
    tags: list[str] = Field(default_factory=list)
    port: int = Field(ge=1, le=65535)

    @field_validator("name")
    @classmethod
    def _no_whitespace(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v
```

Pydantic v2 is the current API (`pydantic` ≥ 2.0). Key calls:

- `Model.model_validate(data)` — validate/coerce a dict or object.
- `Model.model_validate_json(s)` — parse + validate a JSON string directly.
- `model.model_dump()` / `model.model_dump_json()` — serialize to dict / JSON.
- `Field(...)` — constraints and defaults (`min_length`, `ge`, `default_factory`).
- `@field_validator("x")` — per-field post-validation transforms/checks.
- `@computed_field` — a read-only property exposed in `model_dump()`.
- `ConfigDict` / `model_config` — e.g. `model_config = ConfigDict(frozen=True, extra="forbid")`.

Nesting composes cleanly: a field whose type is another `BaseModel` is validated
recursively, so you get a typed, validated object graph from JSON in one call.

## Decision table: dataclass vs Pydantic

| Concern | `@dataclass` | Pydantic `BaseModel` |
|---------|--------------|----------------------|
| Runtime validation / coercion of inputs | ✗ none | ✓ automatic, per-field |
| JSON round-trip | manual `asdict`/`json.dumps` | `model_dump_json()` / `model_validate_json` |
| Performance (creation in hot loops) | fast, near-plain-class | slower — validation overhead per instantiation |
| Mutable default lists/dicts | foot-gun (see Pitfalls) | `default_factory` handled, but `Field(default_factory=...)` still required |
| Immutable value objects | `frozen=True` | `ConfigDict(frozen=True)` |
| Serialization shape control | manual | rich (`by_alias`, `exclude_unset`, `computed_field`) |
| Syntax/deps | stdlib, zero deps | third-party dependency |

**Rule**: use Pydantic at the **boundary** (HTTP request/response, config files,
API payloads, anything that crosses trust or format), and dataclasses for
internal, already-trusted computation. Don't wrap hot inner loops in Pydantic —
validating the same object ten thousand times in a tight loop is measurable
overhead (see **sqlite-optimization** for the "hot path" mindset).

## `slots=True` benefit + tradeoff

- Benefit: smaller instances (no per-instance `__dict__`), faster attribute
  access, and typos fail loudly.
- Tradeoff: you **cannot add new attributes after creation** — everything must be
  declared up front. After instantiation, `obj.extra = 1` raises
  `AttributeError`. That's usually what you want, but it breaks duck-typed
  "just tack a field on later" code.
- `frozen=True` is orthogonal to `slots=True`: combine them
  (`@dataclass(frozen=True, slots=True)`) for a true value object. Mutating a
  `frozen` dataclass raises `FrozenInstanceError`.

## Mutable default pitfall (concrete bug)

```python
# WRONG — one shared list lives on the class
@dataclass
class Bug:
    tags: list[str] = []


a = Bug()
a.tags.append("x")
b = Bug()
b.tags  # -> ["x"]  !!! shared across all instances
```

```python
# RIGHT — a fresh list per instance
@dataclass
class Good:
    tags: list[str] = field(default_factory=list)
```

This is the single most common dataclass bug: with `= []` the same mutable
object is reused by every instance, so data leaks between objects. Same for
`= {}` and `= set()`. Always `field(default_factory=...)`. (Pydantic sidesteps
raw defaults via its own handling, but still use `Field(default_factory=list)`
for clarity and to avoid a shared default.)

## Keep Pydantic at the boundary

Serialize/validate once at the edges, then move the plain, trusted data into
cheap dataclasses (or primitives) for the inner logic. Two consequences:

1. **Cost**: you pay validation once, not once per internal call.
2. **Clarity**: your domain functions take `Point` dataclasses, not
   `BaseModel` — which keeps a third-party type from leaking through your
   whole codebase and makes the inner code trivially testable.

## Pitfalls

- **Shared mutable defaults** (`= []` / `= {}`): the classic cross-instance
  data-leak bug above — always `default_factory`.
- **`slots=True` blocks late attributes**: declare everything before
  construction or switch to a normal dataclass.
- **Validation overhead in hot loops**: don't re-validate the same object
  repeatedly; validate at the boundary.
- **Pydantic v1 vs v2 API drift**: v2 renamed `parse_obj`→`model_validate`,
  `dict()`→`model_dump()`, `Config`→`model_config`/`ConfigDict`. Pin `pydantic>=2`
  and don't copy v1 snippets.
- **`extra="forbid"` on schemas you don't control**: forbidding unknown keys
  breaks forward-compat when a producer adds a field. Prefer `extra="ignore"`
  (default) unless you explicitly want strictness.

## Checklist

- [ ] Boundary data → Pydantic `BaseModel` (v2 API); internal data → dataclasses.
- [ ] No shared mutable defaults — `field(default_factory=...)` everywhere.
- [ ] `slots=True` (and `frozen=True` for value objects) where appropriate, with up-front attributes.
- [ ] `model_validate_json` for parsing untrusted JSON; `model_dump_json` for output.
- [ ] Validation applied once at the boundary, not in hot inner loops.