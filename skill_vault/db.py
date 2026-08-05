"""SQLite connection helpers plus the process-wide database lock.

FastMCP executes tool calls on a worker threadpool, and the web tier is async.
To avoid sqlite3 cross-thread cursor finalization races, each thread gets its own
SQLite connection to the same file. Multi-statement writes still use one process-
wide re-entrant lock for transaction atomicity. Use ``locked()`` as a context
manager around write transactions.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType
from typing import Any

db_lock = threading.RLock()
_thread_connections_lock = threading.RLock()
_thread_connections: dict[tuple[str, int], sqlite3.Connection] = {}


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


class ConnectionProxy:
    """Proxy that resolves to the current thread's SQLite connection."""

    def __init__(self, path: str) -> None:
        self._path = path

    def _key(self) -> tuple[str, int]:
        return (self._path, threading.get_ident())

    def _current(self) -> sqlite3.Connection:
        key = self._key()
        with _thread_connections_lock:
            db = _thread_connections.get(key)
            if db is None:
                db = connect(self._path)
                _thread_connections[key] = db
            return db

    @property
    def row_factory(self) -> Any:
        return self._current().row_factory

    @row_factory.setter
    def row_factory(self, value: Any) -> None:
        self._current().row_factory = value

    def execute(self, sql: str, parameters: Any = ()) -> sqlite3.Cursor:
        return self._current().execute(sql, parameters)

    def executemany(self, sql: str, seq_of_parameters: Any) -> sqlite3.Cursor:
        return self._current().executemany(sql, seq_of_parameters)

    def executescript(self, sql_script: str) -> sqlite3.Cursor:
        return self._current().executescript(sql_script)

    def commit(self) -> None:
        self._current().commit()

    def rollback(self) -> None:
        self._current().rollback()

    def close(self) -> None:
        key = self._key()
        with _thread_connections_lock:
            db = _thread_connections.pop(key, None)
        if db is not None:
            db.close()

    def __enter__(self) -> sqlite3.Connection:
        return self._current().__enter__()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return self._current().__exit__(exc_type, exc_value, traceback)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._current(), name)


def connect_threadlocal(path: str) -> ConnectionProxy:
    """Return a proxy that uses one cached connection per thread for ``path``."""
    return ConnectionProxy(path)


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
