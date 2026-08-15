## SQLite PRAGMA Quick Reference

### Must-set PRAGMAs (every connection)
```sql
PRAGMA journal_mode=WAL;       -- concurrent readers + 1 writer
PRAGMA foreign_keys=ON;        -- enforce referential integrity
PRAGMA synchronous=NORMAL;     -- safe with WAL, 2-10x faster than FULL
```

### Performance PRAGMAs
```sql
PRAGMA cache_size = -8000;     -- 8 MB page cache (negative = KB)
PRAGMA mmap_size = 268435456;  -- 256 MB memory-mapped I/O
PRAGMA temp_store = MEMORY;    -- temp tables/indices in RAM
```

### Integrity & maintenance
```sql
PRAGMA integrity_check;        -- verify DB isn't corrupted
PRAGMA quick_check;            -- faster, less thorough
PRAGMA optimize;               -- run after significant changes
ANALYZE;                       -- update query planner stats
```

### Index design rules
1. Index FK columns and WHERE/JOIN/ORDER BY columns
2. Composite index `(a, b)` covers `WHERE a=?` AND `WHERE a=? AND b=?` -- NOT `WHERE b=?`
3. Use `EXPLAIN QUERY PLAN` to verify index usage
4. Covering indexes include extra columns to avoid table lookups
5. Don't over-index: each index slows INSERT/UPDATE/DELETE

### Backup (WAL-safe)
```bash
sqlite3 my.db ".backup backup.db"
```
```python
import sqlite3

src = sqlite3.connect("my.db")
dst = sqlite3.connect("backup.db")
src.backup(dst)
dst.close()
src.close()
```
Never copy .db + .wal + .shm files directly while the DB is open.