#!/usr/bin/env python3
"""HTMX + Alpine.js frontend server — no build step, no npm.

Serves a search page with HTMX partial swaps and Alpine client state.
Run: python server.py  →  http://localhost:8080

Requires: pip install fastapi uvicorn jinja2
"""

from __future__ import annotations

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory=".")

# ── Mock data ───────────────────────────────────────────────────────────

ITEMS = [
    "Python programming",
    "JavaScript basics",
    "Docker containers",
    "PostgreSQL queries",
    "Redis caching",
    "HTMX tutorials",
    "Alpine.js reactivity",
    "REST API design",
    "GraphQL queries",
    "WebSocket connections",
]


# ── Routes ──────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"items": ITEMS})


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = Query(default="", max_length=100)):
    is_htmx = request.headers.get("HX-Request") == "true"
    if not q.strip():
        results = ITEMS
    else:
        results = [item for item in ITEMS if q.lower() in item.lower()]

    template = "results.html" if is_htmx else "index.html"
    return templates.TemplateResponse(
        request=request, name=template, context={"items": results, "query": q}
    )


# ── Template files (write on first run) ────────────────────────────────

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HTMX + Alpine Demo</title>
<script src="https://unpkg.com/htmx.org@1.9.12" defer></script>
<script src="https://unpkg.com/alpinejs@3.14.1" defer></script>
<script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen p-8" x-data="{ dark: false }">
<div class="max-w-xl mx-auto">
  <div class="flex justify-between items-center mb-6">
    <h1 class="text-2xl font-bold text-gray-800">Search Demo</h1>
    <button @click="dark = !dark"
            :class="dark ? 'bg-gray-700 text-white' : 'bg-gray-200 text-gray-700'"
            class="px-3 py-1 rounded text-sm">Toggle Dark</button>
  </div>

  <!-- Search form: HTMX-driven, triggers on keyup -->
  <input type="search" name="q" placeholder="Type to search..."
         hx-get="/search" hx-trigger="keyup changed delay:200ms"
         hx-target="#results" hx-swap="innerHTML"
         class="w-full px-4 py-3 border border-gray-300 rounded-lg mb-4
                focus:outline-none focus:ring-2 focus:ring-blue-500">

  <!-- HTMX swap target -->
  <div id="results">
    {% include 'results.html' %}
  </div>
</div>
</body>
</html>
"""

RESULTS_HTML = r"""<ul class="space-y-2">
{% if query %}
  <p class="text-sm text-gray-500 mb-2">{{ items|length }} result(s) for "{{ query }}"</p>
{% endif %}
{% for item in items %}
  <li class="p-3 bg-white rounded shadow-sm border border-gray-200
             hover:border-blue-400 transition-colors">
    {{ item }}
  </li>
{% else %}
  <li class="p-4 text-gray-500 text-center">No results found.</li>
{% endfor %}
</ul>
"""

if __name__ == "__main__":
    import os, sys

    # Write templates
    for name, content in [("index.html", INDEX_HTML), ("results.html", RESULTS_HTML)]:
        with open(name, "w") as f:
            f.write(content)
        print(f"Wrote {name}")

    # Only start server if --serve flag passed
    if "--serve" in sys.argv:
        import uvicorn

        uvicorn.run(app, host="0.0.0.0", port=8080)
    else:
        print("Templates written. Run with --serve to start the dev server.")
