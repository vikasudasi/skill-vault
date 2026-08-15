# HTMX Event & Trigger Patterns

## Trigger modifiers

| Modifier | Example | Effect |
|----------|---------|--------|
| `delay:<ms>` | `hx-trigger="keyup delay:300ms"` | Debounce: wait after last event |
| `changed` | `hx-trigger="keyup changed"` | Only fire if value actually changed |
| `every <n>s` | `hx-trigger="every 5s"` | Poll at fixed interval |
| `once` | `hx-trigger="click once"` | Fire once then remove listener |
| `from:<css>` | `hx-trigger="keyup from:input"` | Listen on a different element |
| `throttle:<ms>` | `hx-trigger="keyup throttle:500ms"` | Rate-limit to one per interval |

## Out-of-band (OOB) swaps

Update a different part of the page than `hx-target`:

```html
<!-- Server returns -->
<div id="cart-count" hx-swap-oob="true">5 items</div>
<div>Main result content here</div>
```

The cart-count div is swapped into the matching `#cart-count` in the DOM,
even though the main swap target is different.

## HTMX events (JS listeners)

```js
document.body.addEventListener("htmx:afterSwap", (evt) => {
    console.log("Swapped:", evt.detail.target);
});

document.body.addEventListener("htmx:responseError", (evt) => {
    alert("Request failed: " + evt.detail.xhr.status);
});
```

## Alpine + HTMX integration patterns

- **Alpine for UI state:** dark mode, open panels, validation feedback, form progress
- **HTMX for server data:** searches, form submissions, pagination, live updates
- **Re-init after swap:** If HTMX inserts new Alpine components, dispatch `alpine:init` on the target
- **Never** use Alpine to fetch server data — that's HTMX's job