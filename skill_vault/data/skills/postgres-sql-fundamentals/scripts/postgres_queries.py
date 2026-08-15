#!/usr/bin/env python3
"""PostgreSQL fundamentals: schema, queries, transactions, EXPLAIN, pooling."""

from __future__ import annotations

import os
import sys

try:
    import psycopg
    from psycopg_pool import ConnectionPool
except ImportError:
    print("Install: pip install psycopg psycopg-pool", file=sys.stderr)
    sys.exit(1)

PG_URL = os.getenv("PG_URL", "postgresql://postgres:postgres@localhost:5432/postgres")


def create_schema(conn) -> None:
    """Create a well-typed schema with constraints and indexes."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name       TEXT NOT NULL UNIQUE,
            tags       TEXT[] NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_skills_tags ON skills USING GIN (tags);
    """)
    conn.commit()


def insert_demo_data(conn) -> None:
    """Insert with transactional safety."""
    with conn.transaction():
        conn.execute(
            "INSERT INTO skills (name, tags) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
            ("postgres-sql", ["database", "sql", "fundamentals"]),
        )
        conn.execute(
            "INSERT INTO skills (name, tags) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
            ("python-asyncio", ["python", "concurrency", "async"]),
        )


def query_with_explain(conn) -> None:
    """Run a query with EXPLAIN ANALYZE to inspect the plan."""
    print("=== EXPLAIN ANALYZE ===")
    result = conn.execute("""
        EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
        SELECT name, tags, created_at FROM skills
        WHERE 'sql' = ANY(tags)
        ORDER BY created_at DESC
    """)
    for row in result:
        print(row[0])


def n_plus_1_vs_join(conn) -> None:
    """Demonstrate N+1 vs JOIN - use the latter."""
    print("\n=== JOIN (correct - single query) ===")
    rows = conn.execute("""
        SELECT s.name, s.created_at
        FROM skills s
        WHERE s.tags && ARRAY['sql', 'python']
        ORDER BY s.created_at DESC
    """).fetchall()
    for row in rows:
        print(f"  {row[0]:30s} {row[1]}")


def pool_demo() -> None:
    """Show connection pooling instead of connect-per-query."""
    pool = ConnectionPool(PG_URL, min_size=1, max_size=4, open=True)
    try:
        with pool.connection() as conn:
            rows = conn.execute("SELECT name, created_at FROM skills LIMIT 10").fetchall()
            print(f"\n=== Pool demo: {len(rows)} rows ===")
            for row in rows:
                print(f"  {row[0]:30s} {row[1]}")
    finally:
        pool.close()


def main() -> None:
    try:
        conn = psycopg.connect(PG_URL)
        conn.execute("SELECT 1")
    except Exception as e:
        print(f"Cannot connect to Postgres at {PG_URL}: {e}", file=sys.stderr)
        print("Set PG_URL or start Postgres and try again.", file=sys.stderr)
        sys.exit(1)

    create_schema(conn)
    insert_demo_data(conn)
    query_with_explain(conn)
    n_plus_1_vs_join(conn)
    conn.close()

    pool_demo()


if __name__ == "__main__":
    main()
