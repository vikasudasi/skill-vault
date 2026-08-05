"""Deployment-oriented CLI/config tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from click.testing import CliRunner

from skill_vault.cli import cli
from skill_vault.config import get_settings


def _create_db_with_row(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE sample_data (value TEXT NOT NULL)")
        conn.execute("INSERT INTO sample_data(value) VALUES ('expected')")
        conn.commit()
    finally:
        conn.close()


def test_serve_command_help_mentions_transport() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--transport" in result.output


def test_web_command_help_renders() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["web", "--help"])
    assert result.exit_code == 0


def test_backup_writes_snapshot_and_manifest(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "source.db"
    backups_dir = tmp_path / "backups"
    _create_db_with_row(db_path)

    monkeypatch.setenv("SKILL_VAULT_DB_PATH", str(db_path))
    get_settings.cache_clear()
    try:
        runner = CliRunner()
        result = runner.invoke(cli, ["backup", "--out", str(backups_dir)])
        assert result.exit_code == 0
        snapshots = [path for path in backups_dir.iterdir() if path.is_dir()]
        assert len(snapshots) == 1
        snapshot = snapshots[0]
        assert (snapshot / db_path.name).exists()
        manifest_path = snapshot / "backup.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = manifest["files"]
        assert any(item["name"] == db_path.name for item in files)
    finally:
        get_settings.cache_clear()


def test_restore_restores_snapshot_data(monkeypatch, tmp_path: Path) -> None:
    source_db = tmp_path / "source.db"
    backups_dir = tmp_path / "backups"
    restored_db = tmp_path / "restored.db"
    _create_db_with_row(source_db)

    monkeypatch.setenv("SKILL_VAULT_DB_PATH", str(source_db))
    get_settings.cache_clear()
    try:
        runner = CliRunner()
        backup_result = runner.invoke(cli, ["backup", "--out", str(backups_dir)])
        assert backup_result.exit_code == 0
        snapshot_dirs = [path for path in backups_dir.iterdir() if path.is_dir()]
        assert len(snapshot_dirs) == 1
        snapshot_dir = snapshot_dirs[0]

        restore_result = runner.invoke(
            cli,
            ["restore", str(snapshot_dir), "--db-path", str(restored_db)],
        )
        assert restore_result.exit_code == 0
        conn = sqlite3.connect(str(restored_db))
        try:
            row = conn.execute("SELECT value FROM sample_data").fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] == "expected"
    finally:
        get_settings.cache_clear()


def test_settings_include_mcp_defaults_and_override(monkeypatch) -> None:
    monkeypatch.delenv("SKILL_VAULT_MCP_HOST", raising=False)
    monkeypatch.delenv("SKILL_VAULT_MCP_PORT", raising=False)
    monkeypatch.delenv("SKILL_VAULT_WEB_PORT", raising=False)
    get_settings.cache_clear()
    try:
        defaults = get_settings()
        assert defaults.mcp_host == "0.0.0.0"
        assert defaults.mcp_port == 8000
        assert defaults.web_port == 8080
    finally:
        get_settings.cache_clear()

    monkeypatch.setenv("SKILL_VAULT_MCP_PORT", "9999")
    get_settings.cache_clear()
    try:
        overridden = get_settings()
        assert overridden.mcp_port == 9999
    finally:
        get_settings.cache_clear()
