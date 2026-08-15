#!/usr/bin/env python3
"""Typer CLI demo: commands, options, testing hook, and rich output."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="skillctl",
    help="Skill Vault management CLI",
    add_completion=False,
)


@app.command()
def scan(
    path: str = typer.Argument(..., help="Directory to scan"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Recurse subdirectories"),
    max_depth: int = typer.Option(3, "--depth", "-d", min=1, max=10, help="Max recursion depth"),
) -> None:
    """Scan a directory for skill files."""
    p = Path(path)
    if not p.exists():
        typer.echo(f"Error: '{path}' does not exist", err=True)
        raise typer.Exit(code=2)

    files: list[Path] = []
    pattern = "**/*.md" if recursive else "*.md"
    for f in list(p.glob(pattern))[: max_depth * 10]:
        if f.is_file():
            files.append(f)

    if not files:
        typer.echo("No .md files found.")
        raise typer.Exit(code=3)

    typer.echo(f"Found {len(files)} skill file(s):")
    for f in files:
        typer.echo(f"  {f}")


@app.command()
def validate(
    file: str = typer.Argument(..., help="Path to SKILL.md"),
    strict: bool = typer.Option(False, "--strict", help="Error on warnings"),
) -> None:
    """Validate a SKILL.md file."""
    p = Path(file)
    if not p.is_file():
        typer.echo(f"Error: '{file}' not found or not a file", err=True)
        raise typer.Exit(code=2)

    content = p.read_text()
    issues: list[str] = []

    if "---" not in content:
        issues.append("Missing YAML frontmatter")
    if "# " not in content:
        issues.append("Missing level-1 heading")
    if len(content) < 100:
        issues.append("Body too short (<100 chars)")

    if issues:
        for issue in issues:
            typer.echo(f"  [{'ERROR' if strict else 'WARN'}] {issue}", err=True)
        raise typer.Exit(code=1 if strict else 0)
    typer.echo(f"✓ {file} looks valid")


# - Testable entrypoint -


def main(argv: list[str] | None = None) -> None:
    """Callable from tests - no subprocess needed."""
    app(args=argv, standalone_mode=False)


if __name__ == "__main__":
    app()
