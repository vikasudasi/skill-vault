"""Skill Vault command-line interface."""

from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

import click
from rich.console import Console

from skill_vault.auth import AgentContext, AuthService
from skill_vault.bootstrap import build_services
from skill_vault.config import get_settings
from skill_vault.db import connect, locked, run_migrations
from skill_vault.search import Embedder, SearchService, build_store
from skill_vault.seed import discover_seed_dir, recheck_signatures, seed_skills
from skill_vault.server import create_server
from skill_vault.trust import (
    TrustService,
    canonical_payload,
    generate_curator_keypair,
)

console = Console()
err_console = Console(stderr=True)
BACKUP_SCHEMA_VERSION = 1


@click.group(help="Skill Vault command-line interface.")
def cli() -> None:
    """Skill Vault CLI root command."""


def _resolve_db_path(db_path: str | None) -> str:
    settings = get_settings()
    return db_path or settings.db_path


def _vector_sidecar_files(db_path: str) -> list[Path]:
    db_file = Path(db_path).expanduser().resolve()
    if not db_file.parent.exists():
        return []
    patterns = (
        "*.sqlite_vec",
        "*.sqlite_vec-*",
    )
    files: list[Path] = []
    for pattern in patterns:
        files.extend(candidate for candidate in db_file.parent.glob(pattern) if candidate.is_file())
    return sorted({file_path for file_path in files}, key=lambda file_path: file_path.name)


def _copy_sqlite_database(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(str(source))
    target_conn = sqlite3.connect(str(destination))
    try:
        source_conn.backup(target_conn)
    finally:
        target_conn.close()
        source_conn.close()


def _target_sidecar_name(source_name: str, source_db_name: str, target_db_name: str) -> str:
    source_stem = Path(source_db_name).stem
    target_stem = Path(target_db_name).stem
    if source_name.startswith(f"{source_stem}.sqlite_vec"):
        suffix = source_name[len(source_stem) :]
        return f"{target_stem}{suffix}"
    if source_name.startswith(f"{source_db_name}.sqlite_vec"):
        suffix = source_name[len(source_db_name) :]
        return f"{target_db_name}{suffix}"
    return source_name


def _apply_migrations(db_path: str) -> None:
    db = connect(db_path)
    try:
        run_migrations(db, "migrations")
    finally:
        db.close()


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
        super_label = " super" if ctx.is_super_agent else ""
        console.print(
            f"[green]Authenticated:[/green] agent={ctx.agent_id} scope={ctx.scope}{super_label}"
        )
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


@cli.command("seed", help="Seed curated skills from the library dir into the registry.")
@click.option(
    "--dir",
    "seed_dir",
    default=None,
    type=str,
    help="Directory of SKILL.md files (default: settings.seed_dir).",
)
@click.option("--db-path", default=None, type=str, help="Path to the SQLite database file.")
@click.option(
    "--curator-key",
    default=None,
    type=str,
    help="ed25519 private key (base64) to sign verified seed skills (overrides env).",
)
def seed_command(seed_dir: str | None, db_path: str | None, curator_key: str | None) -> None:
    settings = get_settings()
    resolved_db_path = db_path or settings.db_path
    service_settings = replace(settings, db_path=resolved_db_path)
    services = build_services(service_settings)
    selected_seed_dir = seed_dir or settings.seed_dir
    resolved_seed_dir = discover_seed_dir(selected_seed_dir)
    effective_curator_key = curator_key if curator_key is not None else settings.curator_key
    count = seed_skills(services, resolved_seed_dir, effective_curator_key)
    err_console.print(f"Seeded {count} skill(s) from {resolved_seed_dir} into the registry.")


@cli.command("verify", help="Check content integrity + signature for a skill version.")
@click.argument("version_id", type=str)
@click.option("--db-path", default=None, type=str, help="Path to the SQLite database file.")
def verify_command(version_id: str, db_path: str | None) -> None:
    settings = get_settings()
    resolved = db_path or settings.db_path
    db = connect(resolved)
    run_migrations(db, "migrations")
    row = db.execute("SELECT * FROM skill_versions WHERE id = ?", (version_id,)).fetchone()
    if row is None:
        console.print(f"[red]No skill version:[/red] {version_id}")
        raise SystemExit(1)
    payload = canonical_payload(
        name=row["name"],
        description=row["description"],
        tags=json.loads(row["tags"]),
        triggers=json.loads(row["triggers"]),
        meta_json=json.loads(row["meta_json"]),
        body=row["body"],
    )
    trust = TrustService(db, allow_tiers=settings.trust_allow.split(","))
    integrity = trust.verify_integrity(version_id, payload)
    sig = trust.verify_signature(version_id, payload)
    console.print(f"[bold]tier:[/bold] {trust.resolve_tier(version_id)}")
    int_status = "OK" if integrity["ok"] else "MISMATCH"
    console.print(
        f"[bold]integrity:[/bold] {int_status} (stored={integrity['expected'][:12]}… "
        f"actual={integrity['actual'][:12]}…)"
    )
    sig_status = (
        "verified (signed)" if sig["verified"] else ("unsigned" if not sig["signed"] else "INVALID")
    )
    console.print(f"[bold]signature:[/bold] {sig_status}")


@cli.group("curator", help="Curator keypair & signing tools.")
def curator_group() -> None:
    """Curator command group."""


@curator_group.command("gen-key", help="Generate a new curator ed25519 keypair.")
def curator_gen_key_command() -> None:
    private_key, public_key = generate_curator_keypair()
    console.print("[bold yellow]PRIVATE (keep secret, for signing):[/bold yellow]")
    console.print(private_key)
    console.print("[bold green]PUBLIC (share, for verification):[/bold green]")
    console.print(public_key)


@curator_group.command(
    "re-sign",
    help="Re-sign existing bootstrapped global seed skills so they resolve to 'verified'.",
)
@click.option(
    "--dir",
    "seed_dir",
    default=None,
    type=str,
    help="Directory of SKILL.md files (default: settings.seed_dir).",
)
@click.option("--db-path", default=None, type=str, help="Path to the SQLite database file.")
@click.option(
    "--curator-key",
    default=None,
    type=str,
    help="ed25519 private key (base64) to sign with (overrides env).",
)
def curator_resign_command(
    seed_dir: str | None, db_path: str | None, curator_key: str | None
) -> None:
    settings = get_settings()
    resolved_db_path = db_path or settings.db_path
    service_settings = replace(settings, db_path=resolved_db_path)
    services = build_services(service_settings)
    selected_seed_dir = seed_dir or settings.seed_dir
    effective_curator_key = curator_key if curator_key is not None else settings.curator_key
    if not effective_curator_key:
        raise click.ClickException(
            "A curator private key is required: set SKILL_VAULT_CURATOR_KEY or pass --curator-key."
        )
    count = recheck_signatures(services, selected_seed_dir, effective_curator_key)
    err_console.print(f"Re-signed {count} existing seed skill(s) as verified.")


@cli.command("serve", help="Run the Skill Vault MCP server.")
@click.option(
    "--transport",
    type=click.Choice(("stdio", "streamable-http"), case_sensitive=True),
    default="stdio",
    show_default=True,
    help="MCP transport mode.",
)
@click.option("--host", default=None, type=str, help="Bind host (streamable-http mode).")
@click.option("--port", default=None, type=int, help="Bind port (streamable-http mode).")
@click.option("--db-path", default=None, type=str, help="Path to the SQLite database file.")
def serve_command(transport: str, host: str | None, port: int | None, db_path: str | None) -> None:
    settings = get_settings()
    resolved_db_path = db_path or settings.db_path
    resolved_host = host or settings.mcp_host
    resolved_port = port or settings.mcp_port
    _apply_migrations(resolved_db_path)
    service_settings = replace(settings, db_path=resolved_db_path)
    services = build_services(service_settings)
    server = create_server(services)
    if transport == "streamable-http":
        public_host = "<your-host-or-ip>" if resolved_host == "0.0.0.0" else resolved_host
        err_console.print(
            f"[green]Starting MCP streamable HTTP server:[/green] "
            f"http://{public_host}:{resolved_port}/mcp"
        )
    else:
        err_console.print("[green]Starting MCP server over stdio transport.[/green]")
    if transport == "streamable-http":
        server.run(
            transport=cast(Literal["stdio", "http", "sse", "streamable-http"], transport),
            host=resolved_host,
            port=resolved_port,
        )
    else:
        server.run(transport=cast(Literal["stdio", "http", "sse", "streamable-http"], transport))


@cli.command("web", help="Run the Skill Vault web dashboard.")
@click.option("--host", default=None, type=str, help="Bind host.")
@click.option("--port", default=None, type=int, help="Bind port.")
@click.option("--db-path", default=None, type=str, help="Path to the SQLite database file.")
def web_command(host: str | None, port: int | None, db_path: str | None) -> None:
    import uvicorn

    from skill_vault.web import create_app

    settings = get_settings()
    resolved_db_path = db_path or settings.db_path
    resolved_host = host or settings.web_host
    resolved_port = port or settings.web_port
    _apply_migrations(resolved_db_path)
    service_settings = replace(settings, db_path=resolved_db_path)
    services = build_services(service_settings)
    public_host = "<your-host-or-ip>" if resolved_host == "0.0.0.0" else resolved_host
    console.print(
        f"[green]Starting web dashboard:[/green] http://{public_host}:{resolved_port}/dashboard"
    )
    uvicorn.run(create_app(services=services), host=resolved_host, port=resolved_port)


@cli.command("backup", help="Create a timestamped backup snapshot.")
@click.option(
    "--out",
    default="./backups",
    type=click.Path(file_okay=False, path_type=Path),
    show_default=True,
    help="Output directory where snapshots are written.",
)
@click.option("--db-path", default=None, type=str, help="Path to the SQLite database file.")
def backup_command(out: Path, db_path: str | None) -> None:
    resolved_db_path = _resolve_db_path(db_path)
    source_db = Path(resolved_db_path).expanduser().resolve()
    if not source_db.exists():
        raise click.ClickException(f"Database does not exist: {source_db}")

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    snapshot_dir = out.expanduser().resolve() / f"skill-vault-{timestamp}"
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    snapshot_db = snapshot_dir / source_db.name

    with locked():
        _copy_sqlite_database(source_db, snapshot_db)
        copied_files: list[Path] = [snapshot_db]
        for sidecar in _vector_sidecar_files(resolved_db_path):
            destination = snapshot_dir / sidecar.name
            shutil.copy2(sidecar, destination)
            copied_files.append(destination)

    manifest = {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "source_db_path": str(source_db),
        "source_db_name": source_db.name,
        "files": [
            {
                "name": file_path.name,
                "kind": "database" if file_path.name == snapshot_db.name else "vector",
            }
            for file_path in copied_files
        ],
    }
    (snapshot_dir / "backup.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    console.print(f"[green]Backup complete:[/green] {snapshot_dir}")


@cli.command("restore", help="Restore a backup snapshot into the active data path.")
@click.argument("snapshot_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--db-path", default=None, type=str, help="Destination SQLite database file path.")
def restore_command(snapshot_dir: Path, db_path: str | None) -> None:
    manifest_path = snapshot_dir / "backup.json"
    if not manifest_path.exists():
        raise click.ClickException(f"Backup manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise click.ClickException(
            f"Unsupported backup schema version: {manifest.get('schema_version')!r}"
        )
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise click.ClickException("Backup manifest is invalid: missing files list.")

    db_file_entry: dict[str, object] | None = None
    for item in files:
        if isinstance(item, dict) and item.get("kind") == "database":
            db_file_entry = item
            break
    if not isinstance(db_file_entry, dict) or "name" not in db_file_entry:
        raise click.ClickException("Backup manifest is invalid: missing database entry.")

    resolved_db_path = Path(_resolve_db_path(db_path)).expanduser().resolve()
    source_db_path = manifest.get("source_db_path")
    if not isinstance(source_db_path, str):
        raise click.ClickException("Backup manifest is invalid: missing source_db_path.")
    source_db_name = str(manifest.get("source_db_name") or Path(source_db_path).name)
    source_db = snapshot_dir / str(db_file_entry["name"])
    if not source_db.exists():
        raise click.ClickException(f"Snapshot database file missing: {source_db}")

    with locked():
        _copy_sqlite_database(source_db, resolved_db_path)
        target_dir = resolved_db_path.parent
        target_dir.mkdir(parents=True, exist_ok=True)
        for item in files:
            if not isinstance(item, dict):
                continue
            if item.get("kind") != "vector":
                continue
            file_name = item.get("name")
            if not isinstance(file_name, str):
                continue
            src = snapshot_dir / file_name
            if not src.exists():
                raise click.ClickException(f"Snapshot vector file missing: {src}")
            target_name = _target_sidecar_name(file_name, source_db_name, resolved_db_path.name)
            shutil.copy2(src, target_dir / target_name)

        db = connect(str(resolved_db_path))
        try:
            run_migrations(db, "migrations")
        finally:
            db.close()

    console.print(f"[green]Restore complete:[/green] {resolved_db_path}")


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


@agent_group.command(
    "super-agent",
    help="Promote (--on) or demote (--off) an agent's super-agent flag so its API "
    "key may publish/update global (verified) skills.",
)
@click.option("--agent-id", required=True, type=str, help="Agent UUID.")
@click.option("--on/--off", "enable", default=True, help="Set the flag on or off.")
def agent_super_command(agent_id: str, enable: bool) -> None:
    settings = get_settings()
    db = connect(settings.db_path)
    run_migrations(db, "migrations")
    auth = AuthService(db, rate_limit=settings.rate_limit_per_minute)
    exists = db.execute("SELECT 1 FROM agents WHERE id = ?", (agent_id,)).fetchone()
    if exists is None:
        db.close()
        raise click.ClickException(f"No agent found with id {agent_id!r}")
    auth.set_super_agent(agent_id, enable)
    db.close()
    state = "super agent (may publish global verified skills)" if enable else "normal agent"
    console.print(f"[green]Agent {agent_id} is now a {state}.[/green]")


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
