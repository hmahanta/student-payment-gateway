"""
Module Name: constants.py

Purpose:
    Framework-wide constants used across all modules. Centralises magic
    strings, default values, status codes, and folder names so that no
    module carries its own scattered literals.

Author:
    Harish Mahanta

Version:
    1.0.0

Created Date:
    2026-06-18

Last Modified Date:
    2026-06-18

Dependencies:
    None

Usage:
    from core.constants import FolderNames, HealthStatus, Defaults

Configuration Requirements:
    None
"""

from enum import Enum


# ---------------------------------------------------------------------------
# Health-check status tokens
# ---------------------------------------------------------------------------

class HealthStatus(str, Enum):
    """Standardised output tokens for all health check results."""

    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


# ---------------------------------------------------------------------------
# Standard folder names created by FolderManager
# ---------------------------------------------------------------------------

class FolderNames(str, Enum):
    """Canonical folder names used across the framework."""

    INPUT = "input"
    OUTPUT = "output"
    LOGS = "logs"
    REPORTS = "reports"
    ARCHIVE = "archive"
    ERROR = "error"
    TEMP = "temp"
    DATA = "data"
    EXPORTS = "exports"
    IMPORTS = "imports"


# ---------------------------------------------------------------------------
# Framework defaults
# ---------------------------------------------------------------------------

class Defaults:
    """Default configuration values applied when env vars are absent."""

    LOG_LEVEL: str = "INFO"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024   # 10 MB
    LOG_BACKUP_COUNT: int = 5
    DB_PORT: int = 1521
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800             # seconds
    DB_CONNECT_RETRIES: int = 3
    DB_RETRY_DELAY: float = 2.0            # seconds
    MIN_DISK_FREE_GB: float = 1.0
    BASE_FOLDER: str = "."


# ---------------------------------------------------------------------------
# Environment variable key names
# ---------------------------------------------------------------------------

class EnvKeys:
    """Canonical names for environment variable keys."""

    DB_HOST = "DB_HOST"
    DB_PORT = "DB_PORT"
    DB_SERVICE = "DB_SERVICE"
    DB_USER = "DB_USER"
    DB_PASSWORD = "DB_PASSWORD"
    LOG_LEVEL = "LOG_LEVEL"
    INPUT_FOLDER = "INPUT_FOLDER"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"
    REPORT_FOLDER = "REPORT_FOLDER"
    ARCHIVE_FOLDER = "ARCHIVE_FOLDER"
    BASE_FOLDER = "BASE_FOLDER"
    APP_ENV = "APP_ENV"
    APP_NAME = "APP_NAME"


# ---------------------------------------------------------------------------
# Miscellaneous
# ---------------------------------------------------------------------------

FRAMEWORK_VERSION: str = "1.0.0"
FRAMEWORK_NAME: str = "aiframework"
DATE_FORMAT: str = "%Y-%m-%d"
DATETIME_FORMAT: str = "%Y-%m-%d %H:%M:%S"
LOG_DATETIME_FORMAT: str = "%Y-%m-%dT%H:%M:%S"
