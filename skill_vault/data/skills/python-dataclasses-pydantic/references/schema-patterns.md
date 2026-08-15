## Schema Patterns for Dataclasses & Pydantic

### When to use `model_config`

Pydantic v2 `model_config` replaces class-level `Config`:

```python
from pydantic import BaseModel, ConfigDict


class MyModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,  # immutable (hashable)
        extra="forbid",  # reject unknown fields
        str_strip_whitespace=True,
    )
    name: str
```

### Nested models

```python
class Address(BaseModel):
    street: str
    city: str


class User(BaseModel):
    name: str
    address: Address  # validated recursively
```

### Type coercion

Pydantic coerces by default: `"42"` → `42` for `int` fields.
Set `strict=True` on a Field to reject coercion:

```python
age: int = Field(strict=True)
```

### Dataclass-to-Pydantic bridge

```python
from pydantic.dataclasses import dataclass as pydantic_dataclass


@pydantic_dataclass
class ValidatedPoint:
    x: float
    y: float


# Gets validation + JSON for free with dataclass syntax.
```

### Performance note

- `@dataclass(slots=True)` has ~zero overhead and saves 30-50% memory.
- Pydantic validation adds ~10-50µs per model instance.
- Keep Pydantic at boundaries; don't validate inside hot loops.
