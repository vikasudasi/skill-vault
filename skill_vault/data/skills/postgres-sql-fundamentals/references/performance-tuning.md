## Postgres Performance Tuning Reference

### Reading EXPLAIN output (top-down, left-to-right)

| Plan node | Meaning | Action if slow |
|-----------|---------|---------------|
| `Seq Scan` on large table | No index used | Add index on WHERE/JOIN columns |
| `Nested Loop` | Row-by-row join | Often fine for small sets; check for missing index |
| `Hash Join` | Builds hash table | Good for medium-large joins |
| `Merge Join` | Sorted merge | Both sides must be sorted |
| `Index Scan` | Using an index | Expected for filtered queries |

### Index types cheat sheet

| Type | Syntax | Use for |
|------|--------|---------|
| B-tree (default) | `CREATE INDEX` | Equality, range, ORDER BY |
| GIN | `USING GIN` | Array containment, full-text search |
| GiST | `USING GiST` | Geometric, full-text |
| BRIN | `USING BRIN` | Very large tables, naturally ordered data |
| Partial | `... WHERE active = true` | Subset of rows frequently queried |

### Connection pool sizing

```
pool_size = min(max_connections - superuser_reserved, cores * 2)
```

Each connection is a process (~5-10MB). Too many -> swapping. Too few -> queuing.

### VACUUM and statistics
```sql
-- Update planner statistics (run after large data changes)
ANALYZE skills;

-- Full vacuum (reclaims space, updates stats)
VACUUM ANALYZE skills;

-- Check when last vacuumed
SELECT schemaname, relname, last_vacuum, last_autovacuum
FROM pg_stat_user_tables;
```

### Migration checklist
- [ ] `timestamptz` not `timestamp` for zone-aware times
- [ ] `FOREIGN KEY` columns have an index on the referencing side
- [ ] `SELECT` lists explicit columns, not `*`
- [ ] Writes wrapped in transactions with explicit COMMIT/ROLLBACK