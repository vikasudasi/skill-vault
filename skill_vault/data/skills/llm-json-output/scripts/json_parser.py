#!/usr/bin/env python3
"""Reliable JSON extraction from LLM outputs — strip fences, validate, retry.

Demonstrates a complete parse→validate→repair→retry pipeline.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError


# ── Schema ──────────────────────────────────────────────────────────────


class ServiceConfig(BaseModel):
    name: str
    port: int
    enabled: bool = True
    tags: list[str] = []


# ── Core JSON extraction ────────────────────────────────────────────────


def extract_json(text: str) -> str:
    """Extract a JSON object from LLM output, stripping markdown fences.

    Handles:
    - ```json ... ```
    - ``` ... ```
    - Raw JSON with surrounding text
    """
    # Try to find a fenced block first
    fence_patterns = [
        r"```json\s*\n(.*?)\n```",
        r"```\s*\n(\{.*?\})\s*\n```",
    ]
    for pattern in fence_patterns:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            return m.group(1).strip()

    # Fallback: find the outermost {...}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return m.group(0).strip()

    raise ValueError("No JSON object found in text")


def parse_and_validate(raw: str, model: type[BaseModel]) -> Any:
    """Parse JSON string and validate against a Pydantic model."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e

    return model.model_validate(data)


def robust_parse(text: str, model: type[BaseModel], max_retries: int = 3) -> Any:
    """Parse with retry-friendly error messages for re-prompting."""
    errors = []
    for attempt in range(1, max_retries + 1):
        try:
            clean = extract_json(text)
            return parse_and_validate(clean, model)
        except (ValueError, ValidationError) as e:
            errors.append(str(e))
            if attempt == max_retries:
                raise ValueError(
                    f"Failed after {max_retries} attempts.\nErrors: " + "; ".join(errors)
                ) from e
            # Simulated re-prompt (would call LLM here)
            text = f"Fix the JSON. Previous errors: {e}"
    raise RuntimeError("Unreachable")


# ── Demo ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_cases = [
        # Clean JSON
        '{"name": "web", "port": 8080, "enabled": true, "tags": ["http"]}',
        # Markdown-fenced
        '```json\n{"name": "db", "port": 5432, "enabled": true, "tags": ["postgres"]}\n```',
        # Extra text around JSON
        'Here is the config:\n{"name": "cache", "port": 6379, "enabled": false, "tags": ["redis"]}\nEnd.',
        # Invalid: missing required field
        '{"port": 3000}',
    ]

    for i, raw in enumerate(test_cases):
        print(f"\n--- Test {i + 1} ---")
        print(f"Input: {raw[:60]}...")
        try:
            config = robust_parse(raw, ServiceConfig)
            print(f"Parsed: {config.model_dump()}")
        except Exception as e:
            print(f"Failed: {e}")
