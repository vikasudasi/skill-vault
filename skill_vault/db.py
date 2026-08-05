"""SQLite connection helpers plus the process-wide database lock.

FastMCP executes tool calls on a worker threadpool, and the web tier is async, so
a single SQLite connection is used from multiple threads. We therefore (a) open
connections with ``check_same_thread=False`` and (b) serialize **all** database
access through one process-wide RLock (``db_lock``) — SQLite is single-writer and
our service operations are multi-statement, so correctness is bought with a lock
rather than risky concurrent access. Use ``locked()`` as a context manager.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

db_lock = threading.RLock()


@contextmanager
def locked() -> Iterator[threading.RLock]:
    """Serialize access to the shared SQLite connection(s). Reentrant."""
    db_lock.acquire()
    try:
        yield db_lock
    finally:
        db_lock.release()


def connect(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path, check_same_thread=False)
    db.execute("PRAGMA journal_mode=WAL;")
    db.execute("PRAGMA foreign_keys=ON;")
    db.execute("PRAGMA busy_timeout=5000;")
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
