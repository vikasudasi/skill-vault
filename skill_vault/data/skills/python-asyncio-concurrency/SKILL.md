---
name: python-asyncio-concurrency
description: Write correct asyncio Python — event loop, tasks, locking, timeouts, and avoiding blocked/leaked coroutines.
tags: [python, asyncio, concurrency, async, backend]
triggers: [asyncio, async, await, event loop, coroutine, concurrency]
complexity: medium
time_estimate: 45-90 min
prerequisites: [python 3.11]
source: Skill Vault curated library
---

# Correct Python asyncio

Use when writing concurrent async code — background tasks, parallel I/O, or
orchestrating many awaitables without blocking the loop.

## Run and await

```python
import asyncio


async def fetch(url: str) -> str: ...


async def main() -> None:
    results = await asyncio.gather(fetch("a"), fetch("b"))
```

## Never block the loop

One event loop runs all coroutines — a blocking `time.sleep()` or sync I/O inside
a coroutine stalls everything. Use `asyncio.sleep()`, re-encode sync work with
`await asyncio.to_thread(...)`, or push CPU-bound work to a process.

## Tasks and cancellation

- `asyncio.create_task()` schedules background work; keep a reference or it may
  be garbage-collected mid-flight.
- Use `asyncio.timeout(...)` (3.11+) for bounds; handle `TimeoutError`.

## Locking across coroutines

```python
lock = asyncio.Lock()
async with lock:
    ...  # critical section
```

An `asyncio.Lock` is per-loop — a plain `threading.RLock` is for threads and
won't serialize coroutines correctly. Match the lock to your concurrency model.

## Pitfalls

- Forgetting to `await` returns a coroutine that never runs → "coroutine was
  never awaited" warning. Intentional fire-and-forget still needs a task.
- Don't share mutable state across tasks without a lock.
