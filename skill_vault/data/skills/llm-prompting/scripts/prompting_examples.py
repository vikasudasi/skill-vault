#!/usr/bin/env python3
"""Demonstrate effective LLM prompting patterns with structured output constraint."""

from __future__ import annotations

import re
from typing import Optional

# --- Prompt building helpers ---

ROLE_DESCRIPTIONS = {
    "reviewer": "You are a senior Python code reviewer. Only flag actual bugs, not style.",
    "classifier": "You are a text classifier. Output EXACTLY one of the allowed labels.",
    "extractor": "You are a data extractor. Return only JSON with the requested keys.",
}


def build_prompt(
    role_key: str,
    task: str,
    input_text: str,
    output_format: str,
    examples: list[dict[str, str]],
) -> str:
    """Assemble a clean, structured prompt following the 5-element pattern."""
    role = ROLE_DESCRIPTIONS[role_key]
    parts = [f"{role}\n\n{task}\n"]

    # Static few-shot examples first (cache-friendly)
    if examples:
        parts.append("\nExamples:\n")
        for i, ex in enumerate(examples, 1):
            parts.append(f"Input {i}: {ex['in']}\nOutput {i}: {ex['out']}\n")

    # Dynamic input last
    parts.append(f"\nInput:\n{input_text}\n")
    parts.append(f"\n{output_format}")

    return "\n".join(parts)


def constrain_unknown(text: str, default: str = "UNKNOWN") -> str:
    """Enforce a fallback value instead of hallucination."""
    if not text or not text.strip():
        return default
    return text.strip()


def validate_json_keys(data: dict, required: list[str]) -> dict:
    """Ensure output has exactly the requested keys, fill missing with UNKNOWN."""
    return {k: data.get(k, "UNKNOWN") for k in required}


# --- Usage examples (these would be sent to an actual LLM) ---


def demo_reviewer_prompt() -> None:
    prompt = build_prompt(
        role_key="reviewer",
        task="Find the one bug in this code and return only the line number and fix.",
        input_text="x = [1, 2]; x.sort(); x.append(3)",
        output_format='Return: {"line": <int>, "issue": <str>, "fix": <str>}',
        examples=[
            {
                "in": "y = (1,2); y[0] = 3",
                "out": '{"line": 1, "issue": "tuple assignment", "fix": "use a list"}',
            },
        ],
    )
    print("=== Reviewer Prompt ===\n" + prompt + "\n")


def demo_extractor_prompt() -> None:
    prompt = build_prompt(
        role_key="extractor",
        task="Extract name, date, and amount from the invoice text.",
        input_text="Invoice #442: John Smith paid $95.00 on 2025-03-12",
        output_format=(
            "Return JSON with keys: name, date, amount.\n"
            'If any field is missing, use "UNKNOWN".\n'
            "Do not invent data."
        ),
        examples=[],
    )
    print("=== Extractor Prompt ===\n" + prompt + "\n")


def demo_constraint_output() -> None:
    """Show how post-processing enforces constraints regardless of LLM output."""
    llm_output = {"name": "Alice", "date": "2025-01-01"}  # missing amount
    fixed = validate_json_keys(llm_output, ["name", "date", "amount"])
    print(f"Before validation: {llm_output}")
    print(f"After validation:  {fixed}")
    # Also demo the UNKNOWN fallback
    print(f"Empty input fallback: '{constrain_unknown('')}'")


if __name__ == "__main__":
    demo_reviewer_prompt()
    demo_extractor_prompt()
    demo_constraint_output()
