---
name: python-cli-typer
description: Build production-grade Python CLIs with Typer (or Click) — subcommands, options, env config, exit codes, and testing.
tags: [python, cli, typer, click, tooling]
triggers: [cli, command-line, typer, click, argparse, build a cli]
complexity: medium
time_estimate: 30-60 min
prerequisites: [python 3.11, uv or pip]
source: Skill Vault curated library
verify: true
---

# Building Python CLIs with Typer

Use when scaffoldng or extending a Python command-line tool and you want a
maintainable argument surface, clean help, and a testable entrypoint.

## Scaffold

```py
from __future__ import annotations

import typer

app = typer.Typer(add_completion=False)


@app.command()
def scan(path: str, recursive: bool = typer.Option(False, "--recursive", "-r")) -> None:
    """Scan a directory."""
    ...


if __name__ == "__main__":
    app()
```

## Conventions that matter

- Use `--flag` for booleans, `--opt VALUE` for options; put required positional
  args first. Never mix a required option with a positional that can be omitted.
- Read config from env with a small settings dataclass instead of scattering
  `os.getenv` through commands (mirrors Skill Vault's `get_settings`).
- Exit codes: `0` success, `1` runtime/API error, `2` invalid args (click does
  this by default), `3` "no valid results". Raise a typed exception and map it
  in a top-level handler rather than `sys.exit` inline.

## Testing

Expose a `main(argv: list[str]) -> None` that calls `app(args=argv, standalone_mode=False)`.
This lets you invoke commands in-process without spawning a process.

```py
from cli import main


def test_scan_ok():
    with pytest.raises(SystemExit) as e:
        main(["scan", "src"])
    # assert stdout via capsys
```

## Pitfalls

- Typer's `--help` is auto-generated — keep docstrings accurate, they become help.
- For streaming/progress use `rich` (Typer integrates via `rich.markup`), not print.
- Don't make the CLI print secrets or API keys on the happy path.
