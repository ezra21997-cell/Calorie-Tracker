"""
Centralised logging configuration for the trend-scraper application.

Supports two output modes:
  - Plain text (human-readable, default for development)
  - JSON structured logs (recommended for production / log aggregators)

Usage:
    from utils.logging import get_logger

    logger = get_logger(__name__)
    logger.info("Something happened", extra={"source": "reddit"})
"""

import logging
import sys
from typing import Any

try:
    import json_log_formatter  # optional dependency for JSON logs
    _HAS_JSON_FORMATTER = True
except ImportError:
    _HAS_JSON_FORMATTER = False


_CONFIGURED = False


def configure_logging(level: str = "INFO", use_json: bool = False) -> None:
    """
    Configure the root logger once at application startup.

    Args:
        level:    Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        use_json: Emit JSON-structured log lines when True.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(numeric_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)

    if use_json and _HAS_JSON_FORMATTER:
        formatter = json_log_formatter.JSONFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    handler.setFormatter(formatter)
    root.addHandler(handler)
    _CONFIGURED = True


def get_logger(name: str, **kwargs: Any) -> logging.Logger:
    """
    Return a named logger.  Call ``configure_logging()`` once before using.

    Args:
        name:   Typically ``__name__`` of the calling module.
        kwargs: Passed to ``logging.getLogger`` (no-op currently, for future
                use with structured context injection).

    Returns:
        A ``logging.Logger`` instance.
    """
    return logging.getLogger(name)
