---
name: pytest-testing
description: Write maintainable pytest suites — fixtures and scopes, parametrize, tmp_path, monkeypatch, coverage, and a CI-friendly layout.
tags: [python, testing, pytest, fixtures, coverage, backend]
triggers: [pytest, test, fixture, parametrize, coverage, unit test, monkeypatch]
complexity: medium
time_estimate: 45-90 min
prerequisites: [python 3.11, pytest]
source: Skill Vault curated library
verify: true
---

# Pragmatic pytest

Use when writing or extending a Python test suite — unit tests, fixtures, and a
layout that runs cleanly in CI without cross-test contamination.

## Layout

```
tests/
  conftest.py        # shared fixtures/autouse
  fixtures/          # generator helpers (signing, fake stores)
  test_x.py          # one module per area
```

Put shared fixtures in `conftest.py`; keep per-test helpers beside the test that
uses them. A flat `tests/` next to the app package beats a nested mirror.

## Fixtures and scope

Fixtures are dependency-injected via the parameter name. Scope controls how often
the setup runs:

| scope    | runs once per                                            | use for                        |
|----------|----------------------------------------------------------|--------------------------------|
| function | test (default)                                           | most things, isolation         |
| class    | test class                                                | class-level setup              |
| module   | test module                                               | expensive per-module resources |
| session  | whole run                                                 | DB connection, embedder        |

```python
import pytest


@pytest.fixture(scope="function")
def db(tmp_path):
    conn = connect(str(tmp_path / "app.db"))
    yield conn
    conn.close()
```

A fixture that yields gets teardown after the test — prefer `yield` over
returning, so cleanup runs even on assertion failure.

## tmp_path and monkeypatch

- `tmp_path` is a fresh `Path` per test — never hardcode temp dirs.
- `tmp_path / "app.db"` gives each test an isolated DB (Skill Vault does exactly
  this in its seed tests — `connect(str(tmp_path / "app.db"))`).
- `monkeypatch.setattr(module, "attr", value)` patches for one test and restores
  automatically. Patch at the module that *looks up* the name, not where it's defined.

## Parametrize

```python
@pytest.mark.parametrize("count,name", [(3, "a"), (10, "b")])
def test_seed_ingests(count, name): ...
```

One test body, N cases; each failure is reported independently and the test name
includes the params so you can target a single case with `-k`.

## Assert rewriting and markers

pytest rewrites plain `assert` into rich reports — write `assert x == y`, not
manual `if/raise`. Mark slow or external tests so CI can skip them:

```python
@pytest.mark.slow
def test_expensive(): ...
```

Register markers in `pyproject.toml` / `pytest.ini` under
`[tool.pytest.ini_options] markers = ["slow: long-running"]` to silence warnings.

## Coverage

```
pytest --cov=app --cov-report=term-missing
```

Aim high on core logic but require coverage on *your* package only. Skill Vault
targets 85%+ coverage on `skill_vault` and keeps the threshold in its CI so the
gate fails before merge if you regress.

## Unit vs integration

- Unit: isolated, fast, fake the boundaries (fake DB, fake embedder).
- Integration: real components together, slower, use a real (temp) DB.
Keep them separate directories or marks so the fast unit suite stays the default.

## Pitfalls

- Reusing a module-scoped DB across tests leaks state — reset between tests.
- A fixture that looks unused is removed; if it must always run, use
  `@pytest.fixture(autouse=True)`.
- Forgetting teardown leaves files/connections around; `yield`-style teardown runs
  even on failure.
- Don't assert implementation details (exact SQL strings); assert behaviour.
- `assert` inside a helper function won't get pytest's rich diff — keep asserts
  in the test body.

## Verify / Checklist

- [ ] `pytest` runs green with no cross-test contamination
- [ ] Shared setup lives in `conftest.py`; expensive fixtures use a narrow scope
- [ ] No test writes to the repo tree — all temp state goes to `tmp_path`
- [ ] Parametrized cases cover edge/empty/error inputs, not just the happy path
- [ ] Coverage stays above your threshold on your package
