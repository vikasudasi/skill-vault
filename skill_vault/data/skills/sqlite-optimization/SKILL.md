---
name: sqlite-optimization
description: Tune SQLite for server use — WAL mode, foreign keys, indexes, query profiling, and concurrency-safe writes.
tags: [sqlite, database, sql, performance, backend]
triggers: [sqlite, database slow, index, wal, query tuning]
complexity: medium
time_estimate: 30-60 min
prerequisites: [python, sqlite3]
source: Skill Vault curated library
verify: true
---

# SQLite Optimization for Application Use

Use when your SQLite-backed app is slow, hitting lock errors, or you're scaling
a single-file database for concurrent readers.

## Connection setup (do this every time)

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA synchronous=NORMAL;
```

WAL lets readers run concurrently with a single writer; `synchronous=NORMAL` is
safe with WAL and much faster than FULL.

## Indexes

- Index foreign keys and columns used in `WHERE`/`JOIN`/`ORDER BY`.
- A composite index `(a, b)` serves `WHERE a=?` AND `WHERE a=? AND b=?`, not `WHERE b=?`.
- Confirm with `EXPLAIN QUERY PLAN`.

## Concurrency-safe writes

One shared connection with `check_same_thread=False` needs a **single lock**
around any multi-statement transaction — serialize writes through one
`threading.RLock` (see Skill Vault's `db_lock`). Interleaved statements on one
connection raise `cannot start a transaction within a transaction`.

## Profiling

```sql
EXPLAIN QUERY PLAN SELECT ...
.timer on
```

Read the plan left-to-right; a `SCAN` on a big table usually means a missing index.

## Pitfalls

- `PRAGMA journal_mode=WAL` survives per connection, but must be set on the
  connection that does the work — set it once at connect.
- Don't open a new connection per query in a loop; reuse one and lock writes.
- Back up with `sqlite3 .backup` or `conn.backup()` (WAL safe), never by copying the file alone.
