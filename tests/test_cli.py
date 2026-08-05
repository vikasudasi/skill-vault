"""CLI coverage — init, migrate, onboard, whoami, verify, curator, backup/restore, agent mgmt.

Hermetic: commands run against temp DBs; model/store construction (reindex/serve/web)
is mocked so no network/model download occurs at runtime.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

from click.testing import CliRunner

from skill_vault.cli import (
    _copy_sqlite_database,
    _target_sidecar_name,
    _vector_sidecar_files,
    cli,
)
from skill_vault.config import get_settings
from skill_vault.db import connect, run_migrations


def _init_db(path: Path) -> None:
    conn = connect(str(path))
    run_migrations(conn, "migrations")
    conn.close()


# ---- lifecycle: init / migrate / onboard / whoami ---------------------------


def test_init_creates_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "i.db"
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--db-path", str(db_path)])
    assert result.exit_code == 0
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "skills" in tables
        assert "api_keys" in tables
    finally:
        conn.close()


def test_migrate_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "m.db"
    runner = CliRunner()
    assert runner.invoke(cli, ["migrate", "--db-path", str(db_path)]).exit_code == 0
    # second run applies nothing and succeeds
    assert runner.invoke(cli, ["migrate", "--db-path", str(db_path)]).exit_code == 0


def test_onboard_prints_key_once(tmp_path: Path) -> None:
    db_path = tmp_path / "o.db"
    runner = CliRunner()
    result = runner.invoke(cli, ["onboard", "--name", "cli-agent", "--db-path", str(db_path)])
    assert result.exit_code == 0
    assert "Agent created:" in result.output
    assert "sk: sv_" in result.output
    assert "shown only once" in result.output


def test_whoami_resolves_issued_key(tmp_path: Path) -> None:
    db_path = tmp_path / "w.db"
    runner = CliRunner()
    created = runner.invoke(cli, ["onboard", "--name", "wk", "--db-path", str(db_path)])
    raw_key = next(
        line.strip().removeprefix("sk: ")
        for line in created.output.splitlines()
        if "sk: sv_" in line
    )
    result = runner.invoke(cli, ["whoami", "--db-path", str(db_path)], input=raw_key + "\n")
    assert result.exit_code == 0
    assert "Authenticated:" in result.output


# ---- verify -------------------------------------------------------------------


def test_verify_unknown_version_exits(tmp_path: Path) -> None:
    _init_db(tmp_path / "v.db")
    runner = CliRunner()
    result = runner.invoke(cli, ["verify", "nope", "--db-path", str(tmp_path / "v.db")])
    assert result.exit_code == 1
    assert "No skill version" in result.output


def test_verify_known_version(tmp_path: Path) -> None:
    db_path = tmp_path / "v.db"
    _init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO skills(id, name, owner_agent_id, visibility) VALUES ('s1','Sk',NULL,'global')"
    )
    body = "hello body"
    conn.execute(
        "INSERT INTO skill_versions(id, skill_id, version, content_hash, name, description, "
        "tags, triggers, meta_json, body) VALUES ('v1','s1',1,'"
        + "a" * 64
        + "','Sk','d', '[]','[]','{}', ?)",
        (body,),
    )
    conn.execute("UPDATE skills SET current_version_id='v1' WHERE id='s1'")
    conn.commit()
    conn.close()
    runner = CliRunner()
    result = runner.invoke(cli, ["verify", "v1", "--db-path", str(db_path)])
    assert result.exit_code == 0
    assert "integrity:" in result.output
    assert "signature:" in result.output
    assert "unsigned" in result.output


# ---- curator -------------------------------------------------------------------


def test_curator_gen_key_prints_pair() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["curator", "gen-key"])
    assert result.exit_code == 0
    assert "PRIVATE" in result.output
    assert "PUBLIC" in result.output


# ---- backup / restore ----------------------------------------------------------


def test_backup_missing_db_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli, ["backup", "--out", str(tmp_path), "--db-path", str(tmp_path / "nope.db")]
    )
    assert result.exit_code != 0
    assert "does not exist" in result.output


def test_backup_includes_vector_sidecars(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "bk.db"
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    _init_db(db_path)
    # create fake sqlite-vec sidecar files
    (tmp_path / "data").joinpath("bk.db.sqlite_vec").write_text("vec", encoding="utf-8")
    (tmp_path / "data").joinpath("bk.db.sqlite_vec-0").write_text("vec0", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["backup", "--out", str(tmp_path / "out"), "--db-path", str(db_path)]
    )
    assert result.exit_code == 0
    snap = next((tmp_path / "out").glob("skill-vault-*"))
    assert (snap / "bk.db").exists()
    manifest = json.loads((snap / "backup.json").read_text(encoding="utf-8"))
    kinds = {f["kind"] for f in manifest["files"]}
    assert kinds == {"database", "vector"}


def test_restore_roundtrip_with_sidecars(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    db_path = data / "bk.db"
    _init_db(db_path)
    (data / "bk.db.sqlite_vec").write_text("vec", encoding="utf-8")
    out = tmp_path / "out"
    runner = CliRunner()
    assert (
        runner.invoke(cli, ["backup", "--out", str(out), "--db-path", str(db_path)]).exit_code == 0
    )
    snap = next(out.glob("skill-vault-*"))
    dest_dir = tmp_path / "restored"
    dest = dest_dir / "new.db"
    result = runner.invoke(cli, ["restore", str(snap), "--db-path", str(dest)])
    assert result.exit_code == 0
    assert dest.exists()
    # sidecar renamed to match target db stem
    assert (dest_dir / "new.db.sqlite_vec").exists()


def test_restore_missing_manifest_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["restore", str(tmp_path), "--db-path", str(tmp_path / "x.db")])
    assert result.exit_code != 0
    assert "manifest not found" in result.output.lower()


def test_restore_bad_schema_version_errors(tmp_path: Path) -> None:
    snap = tmp_path / "snap"
    snap.mkdir()
    (snap / "backup.json").write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(cli, ["restore", str(snap)])
    assert result.exit_code != 0
    assert "schema version" in result.output


def test_restore_missing_database_entry_errors(tmp_path: Path) -> None:
    snap = tmp_path / "snap"
    snap.mkdir()
    (snap / "backup.json").write_text(
        json.dumps({"schema_version": 1, "files": [{"name": "v.db", "kind": "vector"}]}),
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["restore", str(snap)])
    assert result.exit_code != 0
    assert "database" in result.output.lower()


# ---- backup helper units --------------------------------------------------------


def test_target_sidecar_name_logic(tmp_path: Path) -> None:
    assert _target_sidecar_name("old.db.sqlite_vec-0", "old.db", "new.db") == "new.db.sqlite_vec-0"
    assert _target_sidecar_name("other.sqlite_vec", "old.db", "new.db") == "other.sqlite_vec"


def test_vector_sidecar_files_missing_dir_returns_empty() -> None:
    assert _vector_sidecar_files("/no/such/dir/x.db") == []


def test_copy_sqlite_database(tmp_path: Path) -> None:
    src = tmp_path / "src.db"
    dst = tmp_path / "sub" / "dst.db"
    _init_db(src)
    _copy_sqlite_database(src, dst)
    conn = sqlite3.connect(str(dst))
    try:
        assert conn.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] > 0
    finally:
        conn.close()


# ---- serve / web (model/store construction mocked) ------------------------------


def test_serve_http_passes_host_and_port(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    fake_server = MagicMock(name="server")
    monkeypatch.setattr("skill_vault.cli.create_server", lambda services: fake_server)
    monkeypatch.setattr("skill_vault.cli.build_services", lambda settings=None: MagicMock())
    # point db_path at a temp file so serve uses it (migrations run)
    db_path = tmp_path / "s.db"
    result = runner.invoke(
        cli,
        [
            "serve",
            "--transport",
            "streamable-http",
            "--host",
            "127.0.0.1",
            "--port",
            "9999",
            "--db-path",
            str(db_path),
        ],
    )
    assert result.exit_code == 0
    fake_server.run.assert_called_once()
    kwargs = fake_server.run.call_args.kwargs
    assert kwargs["transport"] == "streamable-http"
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 9999
    # 0.0.0.0 renders as placeholder in the banner
    db_path2 = tmp_path / "s2.db"
    result2 = runner.invoke(
        cli,
        [
            "serve",
            "--transport",
            "streamable-http",
            "--host",
            "0.0.0.0",
            "--db-path",
            str(db_path2),
        ],
    )
    assert "<your-host-or-ip>" in result2.output or "your-host-or-ip" in result2.output


def test_serve_stdio_no_host_port(monkeypatch, tmp_path: Path) -> None:
    fake_server = MagicMock(name="server")
    monkeypatch.setattr("skill_vault.cli.create_server", lambda services: fake_server)
    monkeypatch.setattr("skill_vault.cli.build_services", lambda settings=None: MagicMock())
    runner = CliRunner()
    result = runner.invoke(cli, ["serve", "--db-path", str(tmp_path / "s.db")])
    assert result.exit_code == 0
    kwargs = fake_server.run.call_args.kwargs
    assert kwargs.get("transport") == "stdio"
    assert "host" not in kwargs
    assert "port" not in kwargs


def test_web_command_invokes_uvicorn(monkeypatch, tmp_path: Path) -> None:
    uvicorn_run = MagicMock()
    monkeypatch.setattr("uvicorn.run", uvicorn_run)
    monkeypatch.setattr("skill_vault.web.create_app", lambda services=None: MagicMock())
    monkeypatch.setattr("skill_vault.cli.build_services", lambda settings=None: MagicMock())
    runner = CliRunner()
    result = runner.invoke(
        cli, ["web", "--host", "127.0.0.1", "--port", "8123", "--db-path", str(tmp_path / "w.db")]
    )
    assert result.exit_code == 0
    uvicorn_run.assert_called_once()
    kwargs = uvicorn_run.call_args.kwargs
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8123


# ---- agent management ------------------------------------------------------------


def _set_db_env(monkeypatch, db_path: Path) -> None:
    monkeypatch.setenv("SKILL_VAULT_DB_PATH", str(db_path))
    get_settings.cache_clear()


def test_agent_create_issues_no_key(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "a.db"
    conn = connect(str(db_path))
    run_migrations(conn, "migrations")
    conn.close()
    _set_db_env(monkeypatch, db_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["agent", "create", "--name", "ag"])
    assert result.exit_code == 0
    assert "Created agent:" in result.output
    con = sqlite3.connect(str(db_path))
    try:
        # agent.create must not have issued a key
        assert con.execute("SELECT count(*) FROM api_keys").fetchone()[0] == 0
    finally:
        con.close()


def test_agent_keys_rotate_revoke(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "a.db"
    conn = connect(str(db_path))
    run_migrations(conn, "migrations")
    conn.close()
    _set_db_env(monkeypatch, db_path)
    runner = CliRunner()
    onboard = runner.invoke(cli, ["onboard", "--name", "ag"])
    assert onboard.exit_code == 0
    agent_id = next(
        l.split(":")[1].strip() for l in onboard.output.splitlines() if "Agent created" in l
    )
    raw_key = next(
        line.strip().removeprefix("sk: ")
        for line in onboard.output.splitlines()
        if "sk: sv_" in line
    )
    con = sqlite3.connect(str(db_path))
    key_id = con.execute("SELECT id FROM api_keys ORDER BY created_at DESC LIMIT 1").fetchone()[0]
    con.close()

    keys = runner.invoke(cli, ["agent", "keys", "--agent-id", agent_id])
    assert keys.exit_code == 0
    assert "sv_" in keys.output

    rot = runner.invoke(cli, ["agent", "rotate", "--agent-id", agent_id, "--key-id", key_id])
    assert rot.exit_code == 0
    assert "New key" in rot.output

    rev = runner.invoke(cli, ["agent", "revoke", "--agent-id", agent_id, "--key-id", key_id])
    assert rev.exit_code == 0
    assert "Revoked key" in rev.output

    # the revoked/rotated original key no longer resolves — resolve() raises
    who = runner.invoke(cli, ["whoami"], input=raw_key + "\n")
    assert "Authenticated:" not in who.output
