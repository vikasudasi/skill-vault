## Asyncio Debugging Reference

### Common errors and fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `RuntimeWarning: coroutine was never awaited` | Forgot `await` | Add `await` or `create_task()` |
| `Task was destroyed but it is pending!` | Task GC'd without reference | Keep a reference to every task |
| Event loop blocked / freezes | `time.sleep()` or sync I/O in coroutine | `await asyncio.sleep()` or `to_thread()` |
| `RuntimeError: This event loop is already running` | Nesting `asyncio.run()` | Use one `asyncio.run()` at top level |

### Debug mode
```bash
PYTHONASYNCIODEBUG=1 python app.py
```
Enables: slow callback warnings, unawaited coroutine detection, detailed task dumps.

### Task lifecycle
```
create_task() -> scheduled -> running -> done / cancelled / exception
                                    |
                              await / gather / wait_for
```

### When to use each concurrency tool

| Tool | Use case |
|------|----------|
| `asyncio.gather()` | Run N coroutines concurrently, get all results |
| `asyncio.create_task()` | Fire-and-forget background work |
| `asyncio.wait()` | Wait with timeout, handle partial results |
| `asyncio.as_completed()` | Process results as they arrive |
| `asyncio.to_thread()` | Offload sync/CPU work |
| `asyncio.Lock()` | Serialize access across coroutines |
| `asyncio.Semaphore()` | Limit concurrent access to N coroutines |
| `asyncio.Queue()` | Producer-consumer between coroutines |

### Cancellation pattern
```python
async def cancellable_work():
    try:
        while True:
            await do_work()
    except asyncio.CancelledError:
        await cleanup()  # always run cleanup
        raise  # re-raise to propagate cancellation
```