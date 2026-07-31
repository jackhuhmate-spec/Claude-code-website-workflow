"""
Structured logging for Omniroute.

Provides JSON and text-formatted logging with correlation IDs,
configurable levels, and optional file output with rotation.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from omniroute.config import settings


LOG_RECORD_BUILTIN_ATTRS = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "module", "msecs",
    "message", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName",
}


class JsonFormatter(logging.Formatter):
    """JSON log formatter that outputs structured log records."""

    def __init__(self, *, include_builtins: bool = False) -> None:
        super().__init__()
        self.include_builtins = include_builtins
        self._hostname = None

    def format(self, record: logging.LogRecord) -> str:
        output: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if self.include_builtins:
            for key in LOG_RECORD_BUILTIN_ATTRS:
                val = getattr(record, key, None)
                if val is not None and key not in output:
                    output[key] = val

        # Add extra context from the record dict
        for key, val in record.__dict__.items():
            if key not in LOG_RECORD_BUILTIN_ATTRS and key not in output:
                output[key] = val

        if record.exc_info and record.exc_info[0]:
            output["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
            }

        return json.dumps(output, default=str, ensure_ascii=False)


class CorrelationIDFilter(logging.Filter):
    """Add a correlation ID to every log record for request tracing."""

    def __init__(self, correlation_id: str | None = None) -> None:
        super().__init__()
        self._cid = correlation_id

    @property
    def correlation_id(self) -> str:
        if self._cid is None:
            self._cid = uuid.uuid4().hex[:12]
        return self._cid

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = self.correlation_id
        return True


def get_logger(name: str = "omniroute") -> logging.Logger:
    """Get a logger with the given name.

    Args:
        name: Logger name, typically ``__name__``.

    Returns:
        Configured logger instance.
    """
    return logging.getLogger(name)


def configure_logging(
    *,
    level: str | None = None,
    fmt: str | None = None,
    log_file: str | None = None,
    correlation_id: str | None = None,
) -> None:
    """Configure the root logger for Omniroute.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        fmt: Output format (``json`` or ``text``).
        log_file: Path to log file (``None`` = console only).
        correlation_id: Correlation ID for request tracing.
    """
    log_level = (level or settings.log_level).upper()
    log_format = (fmt or settings.log_format).lower()
    log_path = log_file or settings.log_file

    root = logging.getLogger("omniroute")
    root.setLevel(getattr(logging, log_level, logging.INFO))
    root.handlers.clear()

    if log_format == "json":
        formatter = JsonFormatter(include_builtins=False)
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)-7s] %(correlation_id)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    cid_filter = CorrelationIDFilter(correlation_id=correlation_id)

    if log_path:
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            log_path,
            max_bytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
    else:
        handler = logging.StreamHandler(sys.stdout)

    handler.setFormatter(formatter)
    handler.addFilter(cid_filter)
    root.addHandler(handler)

    # Third-party loggers we want to silence or reduce
    for noisy in ("sqlalchemy.engine", "urllib3", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# Convenience module-level functions
Logger = logging.Logger  # type alias for type hints
LoggerFactory = Callable[[str], Logger]
