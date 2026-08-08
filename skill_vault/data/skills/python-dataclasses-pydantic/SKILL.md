---
name: python-dataclasses-pydantic
description: Model structured Python data with dataclasses and Pydantic — immutable value objects, validation, serialization.
tags: [python, dataclasses, pydantic, data-modeling, backend]
triggers: [dataclass, pydantic, model, structured data, validation]
complexity: low
time_estimate: 20-40 min
prerequisites: [python 3.11]
source: Skill Vault curated library
verify: true
---

# Data Modeling with Dataclasses + Pydantic

Use when a module carries structured records and you want type safety, validation,
or clean JSON round-tripping.

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
(an unknown attribute must be declared).

## Validation + serialization with Pydantic

```python
from pydantic import BaseModel, Field


class SkillInput(BaseModel):
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
```

- Field-level validation + coercion for free.
- `.model_dump_json()` / `.model_validate(...)` for clean JSON.

## When to use which

- Internal, no I/O validation needed → `@dataclass(slots=True)`.
- Boundaries: HTTP bodies, config, API responses → Pydantic `BaseModel`.

## Pitfalls

- Mutating default `list`/`dict` in a dataclass is a classic bug — always use
  `field(default_factory=list)`, never `= []`.
- `@dataclass(slots=True)` disallows adding attributes later; declare everything
  up front.
- Keep Pydantic at the boundary; don't let validation wrap hot inner loops.
