from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL;")
    db.execute("PRAGMA foreign_keys=ON;")
    db.row_factory = sqlite3.Row
    return db


def run_migrations(db: sqlite3.Connection, migrations_dir: str) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        """
    )
    applied = {
        int(row["version"])
        for row in db.execute("SELECT version FROM schema_migrations").fetchall()
    }

    migration_files = sorted(Path(migrations_dir).glob("*.sql"))
    pending: list[tuple[int, Path]] = []
    for file_path in migration_files:
        prefix = file_path.stem.split("_", maxsplit=1)[0]
        version = int(prefix)
        if version not in applied:
            pending.append((version, file_path))

    if not pending:
        return

    with db:
        for version, file_path in pending:
            sql = file_path.read_text(encoding="utf-8")
            db.executescript(sql)
            db.execute(
                "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
                (version,),
            )
