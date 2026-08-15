## Prompt Patterns Reference

### The 5-element structure (in cache-optimal order)

| Position | Element | Purpose | Stability |
|----------|---------|---------|-----------|
| 1 (top) | Role | Sets model persona | Static |
| 2 | Few-shot examples | Teaches expected in/out | Static |
| 3 | Task | One clear instruction | Semi-static |
| 4 | Input | The data to process | Dynamic |
| 5 (bottom) | Output format | Schema/constraints | Semi-static |

### Constraint patterns (prefer these over vague warnings)

| Vague (skip) | Concrete (use) |
|---|---|
| "Be careful with dates" | "Use ISO 8601 format (YYYY-MM-DD)" |
| "Make sure it's valid JSON" | "Return exactly: {\"key\": \"value\"}" |
| "Don't make stuff up" | "If unknown, respond with `UNKNOWN`" |
| "Try to be helpful" | "You may ask up to 2 clarifying questions" |

### System vs User boundary

| System prompt | User message |
|---|---|
| Role, rules, format specs | Per-request task + data |
| Persists across turns | Changes every request |
| Cache-friendly | Varies |

### Quick evaluation checklist
- [ ] 3+ test inputs with known correct answers
- [ ] One variable changed at a time between runs
- [ ] Success rate measured, not "feels right"
- [ ] Edge cases: empty input, minimum length, maximum length, special chars