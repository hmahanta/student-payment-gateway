"""
Module Name: environment_manager.py

Purpose:
    Responsible for locating, loading, and validating the .env file at
    application startup. Provides a simple API for downstream modules to
    assert that required variables are present before the application
    proceeds.

Author:
    Harish Mahanta

Version:
    1.0.0

Created Date:
    2026-06-18

Last Modified Date:
    2026-06-18

Dependencies:
    python-dotenv

Usage:
    from core.environment_manager import EnvironmentManager

    env_manager = EnvironmentManager()
    env_manager.load()
    env_manager.assert_required(["DB_HOST", "DB_USER", "DB_PASSWORD"])

Configuration Requirements:
    .env file in the working directory or a path supplied to the constructor.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

from core.constants import EnvKeys
from core.exception_manager import ConfigurationError
from core.logging_manager import get_logger

log = get_logger(__name__)


class EnvironmentManager:
    """
    Loads environment variables from a .env file and validates that
    required keys are present.

    Attributes:
        env_file: Resolved path to the .env file.
        loaded:   True once ``load()`` has been called successfully.
    """

    # Keys that are mandatory for database-connected applications.
    DATABASE_REQUIRED_KEYS: tuple[str, ...] = (
        EnvKeys.DB_HOST,
        EnvKeys.DB_SERVICE,
        EnvKeys.DB_USER,
        EnvKeys.DB_PASSWORD,
    )

    def __init__(self, env_file: str | Path | None = None) -> None:
        """
        Initialise the manager.

        Args:
            env_file: Path to the .env file.  When ``None`` the manager
                      looks for ``.env`` in the current working directory.
        """
        self.env_file: Path = Path(env_file) if env_file else Path(".env")
        self.loaded: bool = False

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def load(self, override: bool = False) -> None:
        """
        Load the .env file into the process environment.

        Args:
            override: When ``True`` existing environment variables are
                      overwritten by values from the file.  Defaults to
                      ``False`` so that shell-level variables take
                      precedence (useful in CI/CD).

        Raises:
            ConfigurationError: If the .env file does not exist.
        """
        if not self.env_file.exists():
            raise ConfigurationError(
                f".env file not found at: {self.env_file.resolve()}",
                key="env_file",
                error_code="CFG-002",
            )

        load_dotenv(dotenv_path=self.env_file, override=override)
        self.loaded = True
        log.info("Environment loaded from %s", self.env_file.resolve())

    def load_if_exists(self, override: bool = False) -> bool:
        """
        Load the .env file only if it exists; silently skip otherwise.

        Returns:
            ``True`` if the file was found and loaded, ``False`` otherwise.
        """
        if self.env_file.exists():
            self.load(override=override)
            return True
        log.warning(
            ".env file not found at %s — relying on shell environment",
            self.env_file.resolve(),
        )
        return False

    def assert_required(self, keys: Sequence[str]) -> None:
        """
        Verify that every key in *keys* is present (and non-empty) in the
        current environment.

        Args:
            keys: Sequence of environment variable names to validate.

        Raises:
            ConfigurationError: On the first missing or empty variable.
        """
        missing: list[str] = [
            k for k in keys if not os.getenv(k, "").strip()
        ]
        if missing:
            raise ConfigurationError(
                f"Required environment variable(s) not set: {missing}",
                details={"missing_keys": missing},
                error_code="CFG-003",
            )
        log.debug("All required environment variables are present: %s", list(keys))

    def get(self, key: str, default: str | None = None) -> str | None:
        """
        Retrieve an environment variable, optionally returning a default.

        Args:
            key:     Environment variable name.
            default: Value to return when the variable is absent.

        Returns:
            The variable value or *default*.
        """
        return os.getenv(key, default)

    def get_required(self, key: str) -> str:
        """
        Retrieve an environment variable, raising if it is absent or empty.

        Args:
            key: Environment variable name.

        Returns:
            The variable value as a string.

        Raises:
            ConfigurationError: If the variable is missing or empty.
        """
        value = os.getenv(key, "").strip()
        if not value:
            raise ConfigurationError(
                f"Required environment variable '{key}' is not set.",
                key=key,
                error_code="CFG-004",
            )
        return value

    def summary(self) -> dict[str, str]:
        """
        Return a dictionary of non-sensitive configuration values for
        logging and health-check reporting.

        Sensitive keys (PASSWORD, SECRET, TOKEN, KEY) are masked.

        Returns:
            Mapping of env key → value (masked where sensitive).
        """
        sensitive_fragments = {"PASSWORD", "SECRET", "TOKEN", "KEY"}
        result: dict[str, str] = {}
        for key, value in os.environ.items():
            if any(frag in key.upper() for frag in sensitive_fragments):
                result[key] = "***REDACTED***"
            else:
                result[key] = value
        return result
