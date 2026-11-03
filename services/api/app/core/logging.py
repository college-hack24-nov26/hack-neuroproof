"""Minimal JSON logging that avoids protected MRI and credential content."""

from __future__ import annotations

import json
import logging


class JsonFormatter(logging.Formatter):
    """Format API events as structured JSON with a narrow safe field set."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field_name in ("job_id", "status", "request_id"):
            value = getattr(record, field_name, None)
            if value is not None:
                payload[field_name] = value
        return json.dumps(payload, sort_keys=True)


def configure_logging() -> None:
    """Configure application logging once without altering existing handlers."""

    logger = logging.getLogger("cerebrachain")
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
