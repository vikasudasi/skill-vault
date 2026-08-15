## Pytest Fixture Patterns

### Scope decision tree
```
Can this be reused across all tests without contamination?
+-- Yes, and expensive -> session
+-- Yes, per module -> module
+-- Only per class -> class
+-- No, needs isolation -> function (default)
```

### Teardown: always use `yield`
```python
@pytest.fixture
def resource():
    obj = acquire()  # setup
    yield obj  # test runs
    obj.release()  # teardown - runs even on assertion failure
```

### tmp_path vs hardcoded temp
```python
# BAD: concurrent runs collide, never cleaned
BAD = "/tmp/my_test.db"


# GOOD: isolated, auto-cleaned
def test_x(tmp_path):
    db = tmp_path / "test.db"
```

### autouse fixtures (use sparingly)
```python
@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    """Always mock LOG_LEVEL in tests - no test needs to request this."""
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
```

### Conftest.py placement
| Fixture scope | Where to put it |
|---|---|
| Used by 1 test file | In that file |
| Used by 2+ files in same dir | `conftest.py` in that dir |
| Used project-wide | Root `tests/conftest.py` |

### Coverage config (pyproject.toml)
```toml
[tool.coverage.run]
source = ["skill_vault"]
omit = ["tests/*"]

[tool.coverage.report]
fail_under = 85
exclude_lines = ["pragma: no cover", "if TYPE_CHECKING:"]
```