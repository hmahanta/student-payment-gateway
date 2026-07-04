"""
Module Name: exception_manager.py

Purpose:
    Defines the complete custom exception hierarchy for the aiframework.
    All application, infrastructure, and domain errors inherit from
    ApplicationError so that callers can catch at any desired granularity.

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
    from core.exception_manager import (
        ApplicationError,
        ConfigurationError,
        DatabaseConnectionError,
        ValidationError,
        FileProcessingError,
    )

    raise ConfigurationError("DB_HOST is not set", key="DB_HOST")

Configuration Requirements:
    None
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Base exception
# ---------------------------------------------------------------------------

class ApplicationError(Exception):
    """
    Base class for all aiframework exceptions.

    Attributes:
        message:   Human-readable description of the error.
        details:   Optional structured context (dict, list, etc.).
        error_code: Optional machine-readable code for downstream handling.
    """

    def __init__(
        self,
        message: str,
        details: Any = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message: str = message
        self.details: Any = details
        self.error_code: str | None = error_code

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, "
            f"error_code={self.error_code!r}, "
            f"details={self.details!r})"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise the exception to a loggable / JSON-safe dictionary."""
        return {
            "exception_type": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# Infrastructure exceptions
# ---------------------------------------------------------------------------

class ConfigurationError(ApplicationError):
    """
    Raised when a required configuration value is missing, invalid, or
    conflicts with another setting.

    Args:
        message: Description of the configuration problem.
        key:     The configuration key that caused the error.
    """

    def __init__(
        self,
        message: str,
        key: str | None = None,
        details: Any = None,
        error_code: str = "CFG-001",
    ) -> None:
        super().__init__(message, details=details, error_code=error_code)
        self.key: str | None = key

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base["key"] = self.key
        return base


class DatabaseConnectionError(ApplicationError):
    """
    Raised when the framework cannot establish or maintain a database
    connection after exhausting retry attempts.

    Args:
        message: Description of the connectivity failure.
        host:    Target database host (redacted in logs automatically).
        port:    Target database port.
    """

    def __init__(
        self,
        message: str,
        host: str | None = None,
        port: int | None = None,
        details: Any = None,
        error_code: str = "DB-001",
    ) -> None:
        super().__init__(message, details=details, error_code=error_code)
        self.host: str | None = host
        self.port: int | None = port

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base["host"] = self.host
        base["port"] = self.port
        return base


class DatabaseQueryError(ApplicationError):
    """
    Raised when a SQL statement fails during execution.

    Args:
        message: Description of the query failure.
        query:   The SQL query that failed (may be truncated for safety).
    """

    def __init__(
        self,
        message: str,
        query: str | None = None,
        details: Any = None,
        error_code: str = "DB-002",
    ) -> None:
        super().__init__(message, details=details, error_code=error_code)
        self.query: str | None = query


# ---------------------------------------------------------------------------
# Domain / business exceptions
# ---------------------------------------------------------------------------

class ValidationError(ApplicationError):
    """
    Raised when input data fails business or schema validation rules.

    Args:
        message: Human-readable validation failure description.
        field:   The field or attribute that failed validation.
        value:   The offending value (avoid logging sensitive data).
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any = None,
        details: Any = None,
        error_code: str = "VAL-001",
    ) -> None:
        super().__init__(message, details=details, error_code=error_code)
        self.field: str | None = field
        self.value: Any = value

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base["field"] = self.field
        # Never store raw passwords or tokens in error context.
        base["value"] = str(self.value) if self.value is not None else None
        return base


class FileProcessingError(ApplicationError):
    """
    Raised when a file cannot be read, written, parsed, or archived.

    Args:
        message:   Description of the file-processing failure.
        file_path: Path of the file that caused the error.
    """

    def __init__(
        self,
        message: str,
        file_path: str | None = None,
        details: Any = None,
        error_code: str = "FILE-001",
    ) -> None:
        super().__init__(message, details=details, error_code=error_code)
        self.file_path: str | None = file_path

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base["file_path"] = self.file_path
        return base


class HealthCheckError(ApplicationError):
    """
    Raised when a mandatory health-check assertion fails at startup.

    Args:
        message: Description of the failed health check.
        check:   Name of the check that failed.
    """

    def __init__(
        self,
        message: str,
        check: str | None = None,
        details: Any = None,
        error_code: str = "HC-001",
    ) -> None:
        super().__init__(message, details=details, error_code=error_code)
        self.check: str | None = check
