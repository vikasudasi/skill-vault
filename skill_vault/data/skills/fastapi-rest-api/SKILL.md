---
name: fastapi-rest-api
description: Build a FastAPI REST API — routers, Pydantic models, dependency injection, error handling, and testing.
tags: [fastapi, python, rest, api, backend]
triggers: [fastapi, rest api, endpoint, uvicorn, openapi]
complexity: medium
time_estimate: 45-90 min
prerequisites: [python 3.11, fastapi, uvicorn]
source: Skill Vault curated library
---

# Building a FastAPI REST API

Use when exposing an HTTP API: resources, validation, OpenAPI docs, and clean error
responses.

## Structure

```
app/
  main.py        # FastAPI() + include_router
  routers/
    skills.py    # APIRouter
  schemas.py     # Pydantic request/response models
```

```python
from fastapi import APIRouter

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("/{skill_id}")
def get_skill(skill_id: str) -> dict: ...
```

## Dependency injection

Resolve auth/db via `Depends` so handlers stay thin and testable:

```python
def get_db():
    yield conn


@router.get("/{id}")
def read(db=Depends(get_db)): ...
```

## Error handling

Raise `HTTPException(status_code=404, detail="...")`, or map domain exceptions
to status codes in a small handler so handlers never leak internals.

## Testing

```python
from fastapi.testclient import TestClient


def test_create():
    client = TestClient(app)
    r = client.post("/skills", json={...})
    assert r.status_code == 201
```

## Pitfalls

- Declare response models to get typed OpenAPI and docs.
- Use `Depends` for shared setup instead of globals — it enables override in tests.
- Don't put business logic in routers; keep them as thin transport layer.
