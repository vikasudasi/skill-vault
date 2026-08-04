"""Skill Vault command-line interface."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from skill_vault.auth import AgentContext, AuthService
from skill_vault.config import get_settings
from skill_vault.db import connect, run_migrations
from skill_vault.search import Embedder, SearchService, build_store

console = Console()


@click.group(help="Skill Vault command-line interface.")
def cli() -> None:
    """Skill Vault CLI root command."""


@cli.command("init", help="Initialize the database and apply baseline schema migrations.")
@click.option("--db-path", default=None, type=str, help="Path to the SQLite database file.")
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
@click.option("--db-path", default=None, type=str, help="Path to the SQLite database file.")
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


@cli.command("onboard", help="Create an agent and issue its first API key (shown once).")
@click.option("--name", required=True, type=str, help="Human-friendly agent name.")
@click.option("--db-path", default=None, type=str, help="Path to the SQLite database file.")
def onboard_command(name: str, db_path: str | None) -> None:
    settings = get_settings()
    resolved = db_path or settings.db_path
    db = connect(resolved)
    run_migrations(db, "migrations")
    auth = AuthService(db, rate_limit=settings.rate_limit_per_minute)
    result = auth.onboard(name)
    console.print(f"[green]Agent created:[/green] {result.agent_id}")
    console.print("[bold yellow]Save this key now — it is shown only once:[/bold yellow]")
    console.print(f"  sk: {result.raw_key}")
    console.print(f"  prefix: {result.key_prefix}")


@cli.command(
    "whoami",
    help="Resolve an API key to an agent identity (verifies the credential).",
)
@click.password_option(confirmation_prompt=False, help="The raw API key (e.g. sv_...).")
@click.option("--db-path", default=None, type=str, help="Path to the SQLite database file.")
def whoami_command(db_path: str | None, password: str) -> None:
    settings = get_settings()
    resolved = db_path or settings.db_path
    db = connect(resolved)
    run_migrations(db, "migrations")
    auth = AuthService(db, rate_limit=settings.rate_limit_per_minute)
    ctx: AgentContext = auth.resolve(password)
    if ctx.is_authenticated:
        console.print(f"[green]Authenticated:[/green] agent={ctx.agent_id} scope={ctx.scope}")
    else:
        console.print("[yellow]Guest[/yellow] (no credential resolved)")


@cli.command("reindex", help="(Re)embed all skill versions into the vector index.")
@click.option("--db-path", default=None, type=str, help="Path to the SQLite database file.")
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


@cli.command("seed", help="Seed curated skills into the registry (stub).")
def seed_command() -> None:
    console.print("[yellow]seed not implemented[/yellow]")


@cli.command("serve", help="Run local Skill Vault services (stub).")
def serve_command() -> None:
    console.print("serve not implemented")


@cli.group("agent", help="Agent identity and API key management commands.")
def agent_group() -> None:
    """Agent command group."""


@agent_group.command("create", help="Create an agent identity (no key is issued).")
@click.option("--name", required=True, type=str, help="Human-friendly agent name.")
def agent_create_command(name: str) -> None:
    settings = get_settings()
    db = connect(settings.db_path)
    run_migrations(db, "migrations")
    auth = AuthService(db, rate_limit=settings.rate_limit_per_minute)
    console.print(f"[green]Created agent:[/green] {auth.create_agent(name)}")


@agent_group.command("keys", help="List API keys issued to an agent.")
@click.option("--agent-id", required=True, type=str, help="Agent UUID.")
def agent_keys_command(agent_id: str) -> None:
    settings = get_settings()
    db = connect(settings.db_path)
    run_migrations(db, "migrations")
    auth = AuthService(db, rate_limit=settings.rate_limit_per_minute)
    for key in auth.list_keys(agent_id):
        status = "revoked" if key.revoked_at else "active"
        console.print(f"  {key.key_prefix}  {status}  (last_used={key.last_used_at!r})")


@agent_group.command("rotate", help="Rotate a key: issue a fresh key and revoke the old one.")
@click.option("--agent-id", required=True, type=str, help="Agent UUID.")
@click.option("--key-id", required=True, type=str, help="Key UUID to rotate.")
def agent_rotate_command(agent_id: str, key_id: str) -> None:
    settings = get_settings()
    db = connect(settings.db_path)
    run_migrations(db, "migrations")
    auth = AuthService(db, rate_limit=settings.rate_limit_per_minute)
    issued = auth.rotate_key(agent_id, key_id)
    console.print("[bold yellow]New key (old revoked):[/bold yellow]")
    console.print(f"  sk: {issued.raw_key}")


@agent_group.command("revoke", help="Revoke an API key. Revoked keys are denied.")
@click.option("--agent-id", required=True, type=str, help="Agent UUID.")
@click.option("--key-id", required=True, type=str, help="Key UUID to revoke.")
def agent_revoke_command(agent_id: str, key_id: str) -> None:
    settings = get_settings()
    db = connect(settings.db_path)
    run_migrations(db, "migrations")
    auth = AuthService(db, rate_limit=settings.rate_limit_per_minute)
    auth.revoke_key(agent_id, key_id)
    console.print(f"[green]Revoked key:[/green] {key_id}")
