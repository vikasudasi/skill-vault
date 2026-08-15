## Testing Typer CLI Apps

### In-process testing pattern
```python
def test_scan_ok():
    with pytest.raises(SystemExit) as exc_info:
        main(["scan", "src/"])
    assert exc_info.value.code == 0


def test_scan_missing_dir():
    with pytest.raises(SystemExit) as exc_info:
        main(["scan", "/nonexistent"])
    assert exc_info.value.code == 2
```

### Capturing stdout/stderr
```python
def test_validate_output(capsys):
    with pytest.raises(SystemExit):
        main(["validate", "valid_skill.md"])
    captured = capsys.readouterr()
    assert "looks valid" in captured.out
```

### Exit code conventions
| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Runtime/API error |
| 2 | Invalid arguments (Typer default) |
| 3 | No valid results found |

### Rich integration
```python
from rich.console import Console

console = Console()


@app.command()
def report():
    console.print("[green]OK[/green] All checks passed")
    console.print("[red]FAIL[/red] 3 issues found")
```

### Environment/config pattern
```python
@dataclass
class Settings:
    api_url: str = "http://localhost:8000"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            api_url=os.getenv("API_URL", cls.api_url),
            log_level=os.getenv("LOG_LEVEL", cls.log_level),
        )
```