#!/usr/bin/env python3
"""SQLite optimization demo: WAL mode, indexes, concurrency-safe writes.

Creates a test DB, inserts 10k rows, compares query plans with/without indexes,
and demonstrates the threading.RLock write-serialization pattern.
"""

from __future__ import annotations

import sqlite3
import threading
import time


def setup_db(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            amount REAL NOT NULL,
            status TEXT NOT NULL
        );
    """)
    conn.commit()


def seed_data(conn: sqlite3.Connection, n: int = 10_000) -> None:
    conn.execute("DELETE FROM orders")
    conn.execute("DELETE FROM users")
    statuses = ["pending", "shipped", "delivered", "cancelled"]
    for i in range(n):
        conn.execute(
            "INSERT INTO users (id, name, email, created_at) VALUES (?,?,?,?)",
            (i + 1, f"user_{i}", f"user{i}@example.com", "2024-01-01"),
        )
        conn.execute(
            "INSERT INTO orders (user_id, amount, status) VALUES (?,?,?)",
            (i + 1, round((i % 100) * 1.5, 2), statuses[i % 4]),
        )
    conn.commit()


def explain(conn: sqlite3.Connection, query: str) -> str:
    rows = conn.execute(f"EXPLAIN QUERY PLAN {query}").fetchall()
    return "\n".join(f"  {r[0]}|{r[1]}|{r[2]}|{r[3]}" for r in rows)


def main() -> None:
    conn = setup_db()
    create_tables(conn)
    seed_data(conn)

    query = """
        SELECT u.name, o.amount, o.status
        FROM users u JOIN orders o ON u.id = o.user_id
        WHERE o.status = 'shipped' AND o.amount > 50
        ORDER BY o.amount DESC
        LIMIT 10
    """

    print("=== Without indexes ===")
    print(explain(conn, query))

    t0 = time.perf_counter()
    conn.execute(query).fetchall()
    t1 = time.perf_counter()
    print(f"Time: {(t1 - t0) * 1000:.1f}ms")

    # Add indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_amount ON orders(amount)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)")
    conn.execute("ANALYZE")

    print("\n=== With indexes ===")
    print(explain(conn, query))

    t0 = time.perf_counter()
    conn.execute(query).fetchall()
    t1 = time.perf_counter()
    print(f"Time: {(t1 - t0) * 1000:.1f}ms")

    # --- Concurrency-safe writes ---
    print("\n=== Thread-safe writes ===")
    db_lock = threading.RLock()

    def safe_insert(n: int) -> None:
        for _ in range(n):
            with db_lock:
                conn.execute("INSERT INTO orders (user_id, amount, status) VALUES (1,1.0,'test')")
                conn.commit()

    threads = [threading.Thread(target=safe_insert, args=(100,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    count = conn.execute("SELECT COUNT(*) FROM orders WHERE status='test'").fetchone()[0]
    print(f"Inserted {count} rows across 4 threads (expected 400)")


if __name__ == "__main__":
    main()
