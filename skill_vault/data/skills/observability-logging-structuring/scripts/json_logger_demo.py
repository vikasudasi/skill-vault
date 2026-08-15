#!/usr/bin/env python3
"""Minimal structured JSON logger with correlation IDs - no framework needed."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from typing import Any


class JsonFormatter(logging.Formatter):
    """Emit one valid JSON object per line with stable keys."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Thread correlation IDs through extra
        for key in ("request_id", "user", "path", "duration_ms", "status"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)

        # Collapse multiline traces
        if record.exc_info and record.exc_info[1]:
            payload["error"] = str(record.exc_info[1])

        return json.dumps(payload, default=str)


def setup_logging(level: str | None = None) -> None:
    """Configure root logger from LOG_LEVEL env var, default INFO."""
    level = level or os.getenv("LOG_LEVEL", "INFO")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


class RequestContext:
    """Middleware-style context manager: generates request_id, logs start/end."""

    def __init__(self, logger: logging.Logger, method: str, path: str, user: str = "anon"):
        self.logger = logger
        self.method = method
        self.path = path
        self.user = user
        self.request_id = uuid.uuid4().hex[:12]
        self.start = time.monotonic()

    def __enter__(self) -> RequestContext:
        self.logger.info(
            "request_start",
            extra={"request_id": self.request_id, "user": self.user, "path": self.path},
        )
        return self

    def __exit__(self, *args: Any) -> None:
        duration = (time.monotonic() - self.start) * 1000
        self.logger.info(
            "request_end",
            extra={
                "request_id": self.request_id,
                "user": self.user,
                "path": self.path,
                "duration_ms": round(duration, 1),
            },
        )

    def log(self, msg: str, **extra: Any) -> None:
        self.logger.info(msg, extra={"request_id": self.request_id, **extra})


# --- Demo ---
if __name__ == "__main__":
    setup_logging("DEBUG")
    logger = logging.getLogger("demo")

    # Simulate a request
    with RequestContext(logger, "GET", "/api/search", "alice") as ctx:
        ctx.log("search_start", query="pytest")
        # ... do work ...
        ctx.log("search_done", results=42)

    # Simulate a warning
    logger.warning(
        "slow_query",
        extra={"request_id": "nocontext", "duration_ms": 1200, "query": "SELECT *"},
    )

    # Simulate an error with traceback
    try:
        1 / 0
    except ZeroDivisionError:
        logger.exception("division_failed")
