#!/usr/bin/env python3
"""Minimal LLM agent with a tool-calling loop — demonstrates the core pattern.

This is a self-contained example: a mock LLM that simulates tool calls,
a tool registry, and an agent loop that plans, calls tools, observes results,
and converges on an answer. No external API keys required.
"""

from __future__ import annotations

import json
from typing import Any


# ── Mock LLM that simulates tool-use responses ──────────────────────────


def mock_llm(system: str, history: list[dict]) -> dict:
    """Simulate an LLM returning either a tool_call or a final answer."""
    last = history[-1]["content"].lower() if history else ""

    if "weather" in last and "london" in last and not any(h.get("role") == "tool" for h in history):
        return {"tool_calls": [{"name": "get_weather", "arguments": {"city": "London"}}]}
    if "greet" in last or "hello" in last:
        return {"tool_calls": [{"name": "get_greeting", "arguments": {"name": "User"}}]}
    # After observing a tool result, produce a final answer
    if any(h.get("role") == "tool" for h in history):
        tool_msgs = [h["content"] for h in history if h.get("role") == "tool"]
        return {"content": f"Based on the data: {tool_msgs[-1]}"}
    return {"content": "I don't understand the request."}


# ── Tool registry ───────────────────────────────────────────────────────


def get_weather(city: str) -> str:
    return json.dumps({"city": city, "temp_c": 15, "condition": "cloudy"})


def get_greeting(name: str) -> str:
    return json.dumps({"greeting": f"Hello, {name}!"})


TOOLS = {
    "get_weather": get_weather,
    "get_greeting": get_greeting,
}


# ── Core agent loop ─────────────────────────────────────────────────────


def run_agent(user_query: str, max_tool_calls: int = 5) -> str:
    """Plan → tool-call → observe → repeat until answer or limit."""
    messages = [
        {"role": "system", "content": "You are a helpful assistant with tools."},
        {"role": "user", "content": user_query},
    ]
    tool_call_count = 0

    while tool_call_count < max_tool_calls:
        response = mock_llm(system=messages[0]["content"], history=messages[1:])

        # Agent decided to produce a final answer
        if "content" in response:
            return response["content"]

        # Agent issued tool calls
        if "tool_calls" in response:
            messages.append({"role": "assistant", "content": json.dumps(response["tool_calls"])})
            for tc in response["tool_calls"]:
                name, args = tc["name"], tc["arguments"]
                if name not in TOOLS:
                    result = json.dumps({"error": f"Unknown tool: {name}"})
                else:
                    try:
                        result = TOOLS[name](**args)
                    except Exception as e:
                        result = json.dumps({"error": str(e)})
                messages.append({"role": "tool", "content": result})
                tool_call_count += 1
            continue

        return "Agent produced no recognizable output."

    return "Max tool calls reached without a final answer."


# ── Demo ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    for query in ["What is the weather in London?", "Say hello to me"]:
        print(f"\nUser: {query}")
        print(f"Agent: {run_agent(query)}")
