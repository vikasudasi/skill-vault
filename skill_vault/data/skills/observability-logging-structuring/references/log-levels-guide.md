## Log Level Decision Table

| Level | Meaning | Example events | Action required |
|-------|---------|---------------|-----------------|
| DEBUG | Verbose detail, opt-in | Variable dump, cache key | None |
| INFO | Normal lifecycle | Request start/end, startup, seed count | None |
| WARNING | Recoverable anomaly | Slow query, retry, unknown header | Monitor trend |
| ERROR | Operation failed, service continues | DB query error, API timeout | Alert if sustained |
| CRITICAL | Service can't function | DB unreachable, config missing | Page immediately |

### What NOT to log at any level
- Passwords, tokens, API keys (even hashed)
- Full request/response bodies
- Session cookies or JWTs
- Credit card numbers, SSNs, PII

### Correlation ID checklist
- [ ] Generated once per request (middleware)
- [ ] Threaded through ALL log lines for that request via `extra`
- [ ] Returned to client as `X-Request-ID` header
- [ ] Logged at request start, end, and every significant event

### Health endpoint patterns
```
/livez  -> "is the process alive?" (no external deps)
/readyz -> "can I serve traffic?" (DB + deps reachable)
/healthz -> combines both (simpler, for single-service)
```

### Quick jq recipes for structured logs
```bash
# Count errors by logger
cat app.log | jq -r 'select(.level=="ERROR") | .logger' | sort | uniq -c

# Find slow requests (>500ms)
cat app.log | jq 'select(.duration_ms > 500)'

# Replay one request's journey
cat app.log | jq 'select(.request_id=="abc123")'
```