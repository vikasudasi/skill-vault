from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from skill_vault.config import get_settings
from skill_vault.db import connect, run_migrations
from skill_vault.search import Embedder, SearchService, build_store

console = Console()


@click.group(help="Skill Vault command-line interface.")
def cli() -> None:
    """Skill Vault CLI root command."""


@cli.command("init", help="Initialize the database and apply baseline schema migrations.")
@click.option(
    "--db-path",
    default=None,
    type=str,
    help="Path to the SQLite database file.",
)
@click.option(
    "--migrations-dir",
    default="migrations",
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory containing SQL migration files.",
)
def init_command(db_path: str | None, migrations_dir: Path) -> None:
    settings = get_settings()
    resolved_db_path = db_path or settings.db_path
    db = connect(resolved_db_path)
    run_migrations(db, str(migrations_dir))
    console.print(f"[green]Initialized database:[/green] {resolved_db_path}")


@cli.command("migrate", help="Apply pending forward-only SQL migrations.")
@click.option(
    "--db-path",
    default=None,
    type=str,
    help="Path to the SQLite database file.",
)
@click.option(
    "--migrations-dir",
    default="migrations",
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory containing SQL migration files.",
)
def migrate_command(db_path: str | None, migrations_dir: Path) -> None:
    settings = get_settings()
    resolved_db_path = db_path or settings.db_path
    db = connect(resolved_db_path)
    run_migrations(db, str(migrations_dir))
    console.print(f"[green]Applied migrations to:[/green] {resolved_db_path}")


@cli.command("seed", help="Seed curated skills into the registry (stub).")
def seed_command() -> None:
    console.print("[yellow]seed not implemented[/yellow]")


@cli.command("reindex", help="(Re)embed all skill versions into the vector index.")
@click.option(
    "--db-path",
    default=None,
    type=str,
    help="Path to the SQLite database file.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Embed all versions (default: only ones missing an embedding).",
)
def reindex_command(db_path: str | None, force: bool) -> None:
    settings = get_settings()
    resolved_db_path = db_path or settings.db_path
    db = connect(resolved_db_path)
    run_migrations(db, "migrations")
    store = build_store(settings.vector_backend, resolved_db_path, settings.pgvector_dsn)
    embedder = Embedder(settings.embed_model)
    service = SearchService(db, store, embedder)
    count = service.reindex_all()
    console.print(f"[green]Reindexed {count} skill version(s).[/green]")


@cli.command("serve", help="Run local Skill Vault services (stub).")
def serve_command() -> None:
    console.print("serve not implemented")


@cli.group("agent", help="Agent identity and API key management commands.")
def agent_group() -> None:
    """Agent command group."""


@agent_group.command("create", help="Create an agent and issue an API key (stub).")
@click.option("--name", required=True, type=str, help="Human-friendly agent name.")
def agent_create_command(name: str) -> None:
    console.print(f"[yellow]agent create not implemented for: {name}[/yellow]")
