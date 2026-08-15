# Dependency Injection Patterns

## Why Depends?

FastAPI's `Depends` resolves shared dependencies (database connections, auth checks,
configuration) before your handler runs. It replaces globals and enables:

- **Test overrides:** swap the real DB for a test one without touching handler code
- **Caching:** dependencies can be cached per-request or per-application lifetime
- **Sub-dependencies:** a dependency can itself depend on another

## Common patterns

```python
# Configuration
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Per-request resources (generators for cleanup)
def get_db():
    conn = create_connection()
    try:
        yield conn
    finally:
        conn.close()


# Auth dependency that chains
def get_current_user(token: str = Depends(oauth2_scheme)):
    return decode_token(token)


@app.get("/me")
def me(user=Depends(get_current_user)):
    return user
```

## Test override recipe

```python
def override_get_db():
    return {"test": True}


app.dependency_overrides[get_db] = override_get_db
# ... run tests ...
app.dependency_overrides.clear()
```

## Error handling: exception handlers

```python
from fastapi import Request
from fastapi.responses import JSONResponse


class DomainError(Exception): ...


@app.exception_handler(DomainError)
async def domain_handler(request: Request, exc: DomainError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})
```