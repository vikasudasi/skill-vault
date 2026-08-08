---
name: htmx-alpine-frontend
description: Build a no-build-step interactive frontend with HTMX partial swaps and Alpine.js state, served from CDN over server-rendered Jinja pages.
tags: [htmx, alpine, javascript, jinja, frontend, no-build, progressive-enhancement]
triggers: [htmx, alpine, hx-get, hx-post, hx-swap, partial, sse, svelte alternative]
complexity: medium
time_estimate: 60-120 min
prerequisites: [jinja2, fastapi, html]
source: Skill Vault curated library
verify: true
---

# HTMX + Alpine Frontend (No Build Step)

Use when you want interactivity (search-as-you-type, partial updates, toggles)
without a bundler, SPA, or build pipeline — the server renders HTML and HTMX
swaps fragments in. This is exactly Skill Vault's frontend: HTMX + Alpine +
highlight.js + Tailwind CDN with no compile step.

## The model

The server stays the source of truth for HTML. HTMX issues requests with headers
(`HX-Request`) and swaps a returned fragment into the DOM; Alpine manages small
client-side state. No API + JSON + client-render ceremony for routine UI.

## HTMX core attributes

| attribute    | meaning                                              |
|--------------|------------------------------------------------------|
| `hx-get`     | issue a GET to the URL (also hx-post/put/delete)     |
| `hx-trigger` | what fires it (`submit`, `change`, `keyup`, `every 5s`) |
| `hx-target`  | which element the response replaces                  |
| `hx-swap`    | how (`innerHTML`, `outerHTML`, `none`)               |
| `hx-boost`   | progressive-enhance normal links/forms to AJAX       |

```html
<form hx-get="/browse" hx-target="#results" hx-trigger="submit">
  <input name="q" hx-get="/browse" hx-trigger="keyup changed delay:300ms"
         hx-target="#results" hx-swap="innerHTML" placeholder="search">
</form>
<div id="results">…</div>
```

## Partial responses

Return a fragment (not the whole page) when the request is HTMX or marked
partial. Skill Vault does this: `browse_results.html` is rendered standalone when
`HX-Request` or `?partial=1` is set, and `{% include %}`-ed into the full page
otherwise — one template, two contexts.

```python
@app.get("/browse")
def browse(q: str = "", partial: int = 0):
    ctx = render_search(q)
    if partial or request.headers.get("HX-Request"):
        return templates.TemplateResponse("browse_results.html", ctx)
    return templates.TemplateResponse("browse.html", ctx)
```

## Out-of-band swap

Swap a fragment that lives elsewhere on the page by adding
`hx-swap-oob="true"` to an element in the response — it's moved into its matching
`id` in the current DOM even if `hx-target` pointed elsewhere.

## Alpine.js for client state

```html
<div x-data="{ dark: false }">
  <button @click="dark = !dark" :class="dark ? 'bg-gray-900' : ''">toggle</button>
  <div x-show="dark" x-transition>…</div>
</div>
```

- `x-data` scopes state; `x-show`/`x-if` visibility; `x-model` two-way binds
  inputs; `x-on` (`@click`) events.
- Use it for UI state (theme, open panels, validation feedback) — not for
  server data retrieval (that's HTMX's job).

## Progressive enhancement + native fallbacks

- Start from working server-rendered HTML; add HTMX/Alpine on top, never instead.
- A link/button must still work (navigate, submit) with JS disabled.
- For clipboard, prefer native `navigator.clipboard.writeText` and fall back to
  `document.execCommand('copy')` on a hidden textarea where the Clipboard API is
  unavailable — don't ship a snippet that silently does nothing.

```js
async function copy(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
  } else {
    const ta = document.createElement("textarea");
    ta.value = text; document.body.appendChild(ta);
    ta.select(); document.execCommand("copy"); ta.remove();
  }
}
```

## CDN, no build step

Load libs via CDN with `defer` (see Skill Vault's `base.html`: htmx 1.9, Alpine
3.x, Tailwind CDN, highlight.js). Load order matters — Alpine must load last so it
sees the final DOM. No npm, no webpack, no source maps.

## Pitfalls

- `hx-trigger="submit"` on a form plus an input `hx-get` can double-fire — pick
  one trigger per control.
- Returning a whole page into a `#results` target (instead of a fragment) wrecks
  the layout — always return partials for swaps.
- Missing `defer` or wrong script order breaks Alpine (components never init) or
  HTMX (swaps no-op) with no console error you'd notice at a glance.
- Using Alpine for server data creates duplicated state and race conditions —
  keep data-fetching on HTMX, state on Alpine.
- `x-transition` needs Alpine's plugin; a bare `#` href or omitted `hx-target`
  silently targets the current element.
- Forgetting the `?partial=1` / `HX-Request` branch makes full pages replace small
  fragments (or vice versa).

## Verify / Checklist

- [ ] Partial templates render standalone on `HX-Request`/`?partial=1` and inline
      otherwise
- [ ] Search/swap targets are correct and return fragments, not full pages
- [ ] Everything works with JS disabled (progressive enhancement intact)
- [ ] Alpine loads last; `defer` on all CDN scripts
- [ ] Clipboard has a native + `execCommand` fallback path
- [ ] No build step required — served straight from the server-rendered HTML