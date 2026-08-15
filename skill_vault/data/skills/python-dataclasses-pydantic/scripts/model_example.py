#!/usr/bin/env python3
"""Demonstrates dataclass + Pydantic modeling with validation and JSON round-tripping.

Covers: @dataclass(slots=True) for internal models, Pydantic BaseModel for I/O
boundaries, and the critical default_factory pattern for mutable defaults.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


# --- Internal model: dataclass with slots ---


@dataclass(slots=True)
class Point:
    x: float
    y: float

    def distance_from_origin(self) -> float:
        return (self.x**2 + self.y**2) ** 0.5


# --- Boundary model: Pydantic with validation ---

try:
    from pydantic import BaseModel, Field, field_validator
except ImportError:
    print("Install pydantic: pip install pydantic")
    raise


class SkillInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=10)
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def tags_must_be_lowercase(cls, v: list[str]) -> list[str]:
        return [t.lower().strip() for t in v]


# --- Usage: dataclass (no validation, fast) ---

p = Point(3.0, 4.0)
print(f"Point distance: {p.distance_from_origin()}")  # 5.0

# --- Usage: Pydantic (validates, serializes) ---

skill = SkillInput(name="Python Tips", description="Useful Python patterns for agents")
print(f"Model dump: {skill.model_dump()}")

# JSON round-trip
raw_json = skill.model_dump_json()
print(f"JSON: {raw_json}")

reloaded = SkillInput.model_validate_json(raw_json)
print(f"Reloaded: {reloaded.name} — {reloaded.description[:30]}...")


# --- Mutable default pitfall (DON'T DO THIS) ---


@dataclass
class BadConfig:
    items: list[str] = []  # BUG: shared across instances!


# Correct:
@dataclass
class GoodConfig:
    items: list[str] = field(default_factory=list)


c1 = GoodConfig()
c2 = GoodConfig()
c1.items.append("a")
print(f"c1: {c1.items}, c2: {c2.items}")  # ['a'], [] — correct isolation

print("\nAll checks passed.")
