#!/usr/bin/env python3
"""Idiomatic asyncio patterns: gather, tasks, timeouts, locks, and to_thread."""

from __future__ import annotations

import asyncio
import time
from typing import Any


# - Safe concurrent I/O with gather -


async def fetch(url: str) -> str:
    """Mock I/O-bound fetch."""
    await asyncio.sleep(0.1)
    return f"<content from {url}>"


async def gather_demo() -> list[str]:
    """Run multiple I/O calls concurrently - total time ~ slowest, not sum."""
    results = await asyncio.gather(
        fetch("https://a.example"),
        fetch("https://b.example"),
        fetch("https://c.example"),
    )
    return list(results)


# - Tasks (keep references!) -


async def task_demo() -> None:
    """Create tasks for background work - MUST keep a reference."""
    tasks: list[asyncio.Task[Any]] = []
    for i in range(3):
        t = asyncio.create_task(fetch(f"task-{i}"), name=f"fetch-{i}")
        tasks.append(t)  # critical: prevent GC

    done, pending = await asyncio.wait(tasks, timeout=5.0)
    for task in pending:
        task.cancel()
    for task in done:
        print(f"  {task.get_name()}: {task.result()}")


# - Timeouts -


async def timeout_demo() -> str | None:
    """Bound an async operation with a deadline."""
    try:
        async with asyncio.timeout(0.05):  # short timeout
            result = await fetch("slow-service")
            return result
    except TimeoutError:
        return "TIMED_OUT"


# - Never block the loop -


def cpu_bound_work(n: int) -> int:
    """Synchronous, CPU-intensive work."""
    return sum(i * i for i in range(n))


async def offload_to_thread_demo() -> int:
    """Move CPU work off the event loop thread."""
    return await asyncio.to_thread(cpu_bound_work, 10_000)


# - Locking across coroutines -


class AsyncCounter:
    """Thread-safe isn't async-safe - use asyncio.Lock for coroutines."""

    def __init__(self) -> None:
        self._value = 0
        self._lock = asyncio.Lock()

    async def increment(self) -> int:
        async with self._lock:
            self._value += 1
            return self._value


async def lock_demo() -> None:
    counter = AsyncCounter()
    results = await asyncio.gather(*[counter.increment() for _ in range(10)])
    print(f"  Final count: {results[-1]} (expected: 10)")


# - Main -


async def main() -> None:
    print("=== gather ===")
    results = await gather_demo()
    print(f"  Retrieved {len(results)} results")

    print("\n=== tasks ===")
    await task_demo()

    print("\n=== timeout ===")
    result = await timeout_demo()
    print(f"  Result: {result}")

    print("\n=== to_thread ===")
    value = await offload_to_thread_demo()
    print(f"  CPU result: {value}")

    print("\n=== lock ===")
    await lock_demo()


if __name__ == "__main__":
    asyncio.run(main())
