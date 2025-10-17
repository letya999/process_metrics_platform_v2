from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional


class JSONFormatter(logging.Formatter):
    """Logging formatter that outputs a single-line JSON object per record.

    Required fields:
      timestamp, level, service, module, message,
      trace_id, user_id, extra
    """

    def __init__(self, service_name: str, datefmt: Optional[str] = None) -> None:
        super().__init__(datefmt=datefmt)
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        timestamp = datetime.utcfromtimestamp(record.created).isoformat() + "Z"
        payload: Dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "service": self.service_name,
            "module": getattr(record, "module", record.name),
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", None),
            "user_id": getattr(record, "user_id", None),
            "extra": {},
        }

        # Attach any additional structured data passed via
        # record.args or record.__dict__
        for attr in ("trace_id", "user_id", "extra"):
            if hasattr(record, attr):
                payload[attr] = getattr(record, attr)

        # If exception info present, include it
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


def get_json_logger(service_name: str, level: int = logging.INFO) -> logging.Logger:
    """Create and return a JSON logger configured for the given service name.

    The logger writes to stderr and uses the `JSONFormatter`.
    """
    logger = logging.getLogger(service_name)
    logger.setLevel(level)
    # Avoid adding multiple handlers if called multiple times
    if not any(
        isinstance(h.formatter, JSONFormatter) for h in logger.handlers if h.formatter
    ):
        handler = logging.StreamHandler()
        handler.setLevel(level)
        handler.setFormatter(JSONFormatter(service_name=service_name))
        logger.addHandler(handler)
    return logger
