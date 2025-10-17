from __future__ import annotations

import json
import logging
from io import StringIO

from common.loggers.json_logger import JSONFormatter, get_json_logger


def capture_log_message(
    formatter: JSONFormatter, level: int = logging.INFO, **record_kwargs
):
    """Helper to capture a single formatted log message as dict."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    logger = logging.getLogger("test_capture_logger")
    logger.handlers = []
    logger.setLevel(level)
    logger.addHandler(handler)

    extra = {}
    for k, v in record_kwargs.items():
        extra[k] = v

    logger.info("test message", extra=extra)
    handler.flush()
    contents = stream.getvalue().strip()
    assert contents, "No log output captured"
    return json.loads(contents)


def test_json_formatter_includes_required_fields():
    fmt = JSONFormatter(service_name="common")
    record = capture_log_message(fmt, trace_id="trace-123", user_id=7)

    assert record["service"] == "common"
    assert record["level"] == "INFO"
    assert record["message"] == "test message"
    assert record["trace_id"] == "trace-123"
    assert record["user_id"] == 7
    assert "timestamp" in record


def test_get_json_logger_idempotent_handlers():
    logger = get_json_logger("myservice")
    # calling again should not add duplicate handlers
    logger2 = get_json_logger("myservice")
    assert logger is logger2
    # there should be exactly one JSONFormatter handler
    json_handlers = [
        h for h in logger.handlers if isinstance(h.formatter, JSONFormatter)
    ]
    assert len(json_handlers) == 1


def test_formatter_includes_exception_info():
    fmt = JSONFormatter(service_name="common")
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(fmt)
    logger = logging.getLogger("test_exc_logger")
    logger.handlers = []
    logger.setLevel(logging.ERROR)
    logger.addHandler(handler)

    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("caught")

    handler.flush()
    contents = stream.getvalue().strip()
    assert contents
    obj = json.loads(contents)
    assert "exc_info" in obj
