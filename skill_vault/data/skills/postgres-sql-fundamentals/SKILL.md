---
name: postgres-sql-fundamentals
description: Postgres fundamentals for when you outgrow SQLite — psql, schema design, constraints, indexes, transactions, EXPLAIN, and connection pooling.
tags: [postgres, sql, database, psql, postgresql, backend]
triggers: [postgres, postgresql, psql, migration from sqlite, connection pool, explain analyze]
complexity: medium
time_estimate: 60-120 min
prerequisites: [sql, python, psycopg]
source: Skill Vault curated library
verify: true
---

# PostgreSQL Fundamentals (When You Outgrow SQLite)

Use when a single-file SQLite DB hits its ceilings — concurrent writes, a shared
server with many clients, or multi-process isolation — and you move to a networked
Postgres. This is the Postgres counterpart to Skill Vault's `sqlite-optimization`;
where that skill tunes a single file, this one runs a real server with
connections, roles, and a query planner.

## SQLite → Postgres decision table

| concern            | SQLite                              | Postgres                          |
|--------------------|-------------------------------------|-----------------------------------|
| concurrency        | single writer, WAL-readers          | MVCC: concurrent reads+writers    |
| deployment         | embedded, one file                  | server, clients connect over TCP  |
| data types         | flexible/affinity                   | strict, rich (arrays, JSONB, enum)|
| migration          | ad-hoc                             | real migrations, DDL transactions |
| backups            | file copy / `.backup`               | `pg_dump` / WAL + PITR            |
| user management    | none                                | roles, grants, row-level security |

Reach for Postgres when you have real concurrent writers, multiple app instances,
or need production guarantees. For a single-user local tool, SQLite (WAL) is still
the right call.

## psql basics

```bash
psql "postgresql://user:pass@host:5432/db"
```

| command     | purpose                     |
|-------------|-----------------------------|
| `\l`        | list databases              |
| `\dt`       | list tables                 |
| `\d table`  | describe table + indexes    |
| `\d+ table` | detailed (incl. sizes)      |
| `\x`        | expanded output (friendly)  |
| `\timing`   | show query time             |
| `\q`        | quit                        |

Connect with a URL or named database; use `PGPASSWORD`/`~/.pgpass` rather than
typing secrets at the prompt in logs.

## Schema design

- **Types**: pick real types (`uuid`, `timestamptz`, `numeric`, `jsonb`) instead
  of overloading text. `timestamptz` stores a point in time; `timestamp` has no
  zone.
- **Constraints**: `NOT NULL`, `CHECK`, `UNIQUE`, and `FOREIGN KEY` are cheap
  integrity — declare them rather than trusting app code.
- **Indexes**: index columns used in `WHERE`/`JOIN`/`ORDER BY`. A B-tree serves
  equality/range; `UNIQUE` and `PRIMARY KEY` create indexes already.
- **Identifiers**: `name` and `data` are not reserved but be careful with
  keywords; quote with `"` only when needed.

```sql
CREATE TABLE skills (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text NOT NULL UNIQUE,
  tags       text[] NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_skills_tags ON skills USING GIN (tags);
```

## Transactions and ACID

Wrap multi-step writes in a transaction so they commit or roll back together:

```sql
BEGIN;
  INSERT INTO skills(name) VALUES ('a');
  UPDATE counts SET n = n + 1 WHERE id = 1;
COMMIT;  -- or ROLLBACK
```

Postgres gives ACID: Atomicity (all-or-nothing), Consistency, Isolation
(concurrent transactions don't see half-states), Durability (committed survives a
crash). Set `isolation_level` deliberately (read committed default; `SERIALIZABLE`
for strict correctness under contention) — don't read uncommitted data.

## EXPLAIN / query planning

```sql
EXPLAIN (ANALYZE, BUFFERS) SELECT ... ;
```

Read top-down, left-to-right: a `Seq Scan` on a large table usually means a
missing index; `Nested Loop` vs `Hash Join` tells you how rows are combined. Add
`ANALYZE` for real row counts/times — and `VACUUM ANALYZE` when stats are stale,
so the planner picks good plans.

## Connections and pooling

Each connection is a server process; opening one per query is expensive and
exhausts `max_connections`. Use a pool (psycopg `pool`/`psycopg_pool`, or
SQLAlchemy pool) sized to your concurrency. Structured logging helps here too:
log pool wait times so you see saturation before it breaks.

## Common pitfalls

- **N+1**: one query per row in a loop instead of a `JOIN` — fix with a single
  joined/`IN` query.
- **Missing index**: a `Seq Scan` on a big table slows every lookup — add the index.
- **`SELECT *`**: pulls unneeded columns (incl. wide `jsonb`), blows up memory —
  name the columns you need.
- Reading connection errors as app bugs: transient `connection refused` under load
  is a pool/max_connections problem, not app logic.
- Forgetting to `commit()` keeps a transaction open and holds locks.
- Using `timestamp` when you need zone-aware times causes off-by-hour bugs.
- A `FOREIGN KEY` without an index on the referencing column makes deletes/joins
  scan.

## Verify / Checklist

- [ ] `psql` connects and `\d` shows real types + constraints + indexes
- [ ] Writes wrapped in transactions; isolation level chosen deliberately
- [ ] `EXPLAIN (ANALYZE, BUFFERS)` shows no `Seq Scan` on hot large tables
- [ ] Connections go through a correctly-sized pool — no connect-per-query
- [ ] No N+1 (`JOIN` used); `SELECT` names explicit columns
- [ ] Backups via `pg_dump`/WAL, not a raw file copy