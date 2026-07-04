"""
Module Name: logging_manager.py

Purpose:
    Enterprise logging factory that provides console logging, rotating file
    logging, and optional JSON-structured logging. Every module across the
    framework obtains its logger via get_logger() so that configuration is
    centralised and consistent.

Author:
    Harish Mahanta

Version:
    1.0.0

Created Date:
    2026-06-18

Last Modified Date:
    2026-06-18

Dependencies:
    python-json-logger  (optional – falls back to text if not installed)

Usage:
    from core.logging_manager import get_logger

    log = get_logger(__name__)
    log.info("Processing started", extra={"record_count": 42})

Configuration Requirements:
    LOG_LEVEL       - DEBUG | INFO | WARNING | ERROR | CRITICAL  (default INFO)
    LOG_FOLDER      - Directory for log files                    (default ./logs)
    LOG_JSON        - "true" to enable JSON-structured logging   (default false)
    APP_NAME        - Prefix used in the log filename            (default app)
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional

from core.constants import Defaults, LOG_DATETIME_FORMAT

# ---------------------------------------------------------------------------
# Optional JSON formatter (python-json-logger)
# ---------------------------------------------------------------------------
try:
    from pythonjsonlogger import jsonlogger  # type: ignore

    _JSON_AVAILABLE = True
except ImportError:
    _JSON_AVAILABLE = False

# ---------------------------------------------------------------------------
# Module-level registry – prevents duplicate handlers on repeated calls
# ---------------------------------------------------------------------------
_configured_loggers: set[str] = set()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_log_folder() -> Path:
    """Return the log folder path, creating it if it does not exist."""
    folder = Path(os.getenv("LOG_FOLDER", "logs"))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _build_text_formatter() -> logging.Formatter:
    """Return a human-readable log formatter."""
    fmt = (
        "%(asctime)s | %(levelname)-8s | %(name)s | "
        "%(filename)s:%(lineno)d | %(message)s"
    )
    return logging.Formatter(fmt=fmt, datefmt=LOG_DATETIME_FORMAT)


def _build_json_formatter() -> logging.Formatter:
    """Return a JSON formatter if pythonjsonlogger is available, else text."""
    if _JSON_AVAILABLE:
        fmt = "%(asctime)s %(levelname)s %(name)s %(filename)s %(lineno)d %(message)s"
        return jsonlogger.JsonFormatter(fmt=fmt, datefmt=LOG_DATETIME_FORMAT)
    # Graceful degradation: fall back to text with a notice.
    return _build_text_formatter()


def _resolve_level() -> int:
    """Parse LOG_LEVEL env var and return the corresponding logging constant."""
    raw = os.getenv("LOG_LEVEL", Defaults.LOG_LEVEL).upper()
    level = getattr(logging, raw, None)
    if not isinstance(level, int):
        level = logging.INFO
    return level


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_logger(
    name: str,
    *,
    log_to_file: bool = True,
    log_json: Optional[bool] = None,
    log_folder: Optional[Path] = None,
) -> logging.Logger:
    """
    Retrieve (or create) a named logger with console and rotating-file handlers.

    The logger is configured only once per process; subsequent calls with the
    same *name* return the cached instance without adding duplicate handlers.

    Args:
        name:         Logger name, typically ``__name__`` of the calling module.
        log_to_file:  Write log records to a rotating file in addition to the
                      console.  Defaults to True.
        log_json:     Override the JSON-output preference.  When ``None`` the
                      value of the ``LOG_JSON`` environment variable is used.
        log_folder:   Override the log directory.  When ``None`` the value of
                      the ``LOG_FOLDER`` environment variable (or ``./logs``)
                      is used.

    Returns:
        A fully configured :class:`logging.Logger` instance.

    Example:
        >>> log = get_logger(__name__)
        >>> log.info("Framework initialised")
    """
    logger = logging.getLogger(name)

    # Return immediately if already configured (idempotent)
    if name in _configured_loggers:
        return logger

    level = _resolve_level()
    logger.setLevel(level)
    logger.propagate = False  # Prevent duplicate records from root logger

    use_json = (
        log_json
        if log_json is not None
        else os.getenv("LOG_JSON", "false").lower() == "true"
    )
    formatter = _build_json_formatter() if use_json else _build_text_formatter()

    # ------------------------------------------------------------------
    # Console handler
    # ------------------------------------------------------------------
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ------------------------------------------------------------------
    # Rotating file handler
    # ------------------------------------------------------------------
    if log_to_file:
        resolved_folder = log_folder or _resolve_log_folder()
        app_name = os.getenv("APP_NAME", "app").replace(" ", "_").lower()
        log_file = resolved_folder / f"{app_name}.log"

        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=Defaults.LOG_MAX_BYTES,
            backupCount=Defaults.LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    _configured_loggers.add(name)
    return logger


def configure_root_logger(level: Optional[str] = None) -> None:
    """
    Apply a minimal configuration to the root logger so that third-party
    libraries emit records at WARNING or above and do not clutter application
    logs.

    Call this once at application startup, before importing any library that
    might call ``logging.basicConfig`` itself.

    Args:
        level: Optional override for the root logger's level string
               (e.g. ``"WARNING"``).  Defaults to WARNING.
    """
    resolved = getattr(logging, (level or "WARNING").upper(), logging.WARNING)
    logging.basicConfig(
        level=resolved,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt=LOG_DATETIME_FORMAT,
        stream=sys.stdout,
    )
