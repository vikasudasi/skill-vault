---
name: observability-logging-structuring
description: Log in a structured, machine-parseable way — JSON lines, levels, correlation ids, request context, and health endpoints for a self-hosted service.
tags: [logging, observability, json logs, structured logging, healthz, metrics, devops]
triggers: [logging, json logs, structured logging, log level, correlation id, health check, observability]
complexity: low
time_estimate: 30-60 min
prerequisites: [python 3.11]
source: Skill Vault curated library
verify: true
---

# Structured Logging for Self-Hosted Services

Use when your service's logs are ungreppable `print()` noise, or when you need to
correlate requests, wrangle levels, and expose a health endpoint. This is how a
service like Skill Vault (uvicorn + structured access logs + `/healthz`) stays
debuggable in production.

## Why structured JSON logs

Random `print(f"got {x}")` lines can't be filtered, correlated, or queried.
Emit one JSON object per line with stable keys so `jq`, log shippers, and your
alerting can actually use them:

```python
import json, logging


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps(
            {
                "ts": self.formatTime(record),
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
            }
        )
```

## Log levels — use them correctly

| level  | use for                                                        |
|--------|----------------------------------------------------------------|
| DEBUG  | verbose detail, only on demand                                |
| INFO   | normal lifecycle: request start/end, seed counts, startup     |
| WARNING| recoverable problems: slow query, retry, unknown header       |
| ERROR  | operation failed but service continues                        |
| CRITICAL | service can't function — process dying                       |

Set the root level from an env var (`LOG_LEVEL`) so prod can raise/lower it
without redeploy. Don't log at INFO, then `print()` debug noise at the same level
— pick the level that matches the event's severity.

## Correlation ids

Give every request a single id threaded through its logs so you can replay one
user's trip:

```python
request_id = request.state.request_id  # set by middleware
logger.info("search", extra={"request_id": request_id})
```

Put `request_id` (+ user, route, duration) in every structured line for that
request. Add `X-Request-ID` to responses so clients can report errors precisely.

## Request context

Log the meaningful dimensions, not the whole request: method, path, status,
duration_ms, request_id, user. A small middleware that wraps each request and
emits one INFO line on completion is worth more than 50 ad-hoc logs.

## Metrics vs logs vs traces

| kind  | answers                              | example                       |
|-------|--------------------------------------|-------------------------------|
| logs  | "what happened"                      | error + corr id + fields      |
| metrics| "how many / how fast / how long"    | request counts, latency, error rate |
| traces| "where did time go across calls"    | one request through services  |

Logs are for individual events; metrics are aggregated counters/histograms
(Prometheus); traces are distributed request paths. Start with logs + a couple of
metrics; add tracing only when you have multiple services.

## Health endpoints

A self-hosted service should expose `/healthz` returning `{"status":"ok"}`
(Skill Vault does exactly this via a small async route). Keep it dependency-free
(no auth) and make it *actually* check liveness: DB reachable, not just "process
is up". Separate `/livez` (process alive) from `/readyz` (deps ready) if upstreams
matter, so load balancers don't drain a healthy-ish node.

## What to log (and not)

Log: request lifecycle, auth decisions (denied, no correlation data), publish
events, seed/ingestion counts, startup config (non-secret), errors with stack.
Never log: passwords, tokens, full request bodies, API keys, session cookies,
or any value a secrets scanner would flag. Sanitize before emitting.

## Pitfalls

- Mixing `print()` with `logging` splits your stream and loses levels/JSON.
- Logging at DEBUG in prod, or INFO-wrapping everything, drowns the signal.
- No correlation id → you can't reassemble a request from scattered lines.
- JSON-with-runtime-branching (a dict that's sometimes a string) breaks parsers —
  keep every line a valid standalone JSON object.
- Multi-line traces (stack traces) break JSON-lines consumers — collapse or
  escape newlines.
- A `/healthz` that returns 200 even when the DB is down gives false "all good".
- Reading secrets back into logs at warn/error is the classic leak.

## Verify / Checklist

- [ ] Logger emits one JSON object per line, greppable via `jq`
- [ ] Correct level per event; root level driven by `LOG_LEVEL`
- [ ] Every request carries a `request_id` threaded through its logs
- [ ] `/healthz` (and `/readyz` if needed) genuinely check liveness
- [ ] No secrets/passwords/tokens in any log line
- [ ] Metrics for counts/latency/error-rate exist (Prometheus-style) if needed