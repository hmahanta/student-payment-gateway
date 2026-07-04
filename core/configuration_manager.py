"""
Module Name: configuration_manager.py

Purpose:
    Singleton configuration manager that loads the .env file, validates
    required keys, applies typed defaults, and exposes a strongly-typed
    ApplicationConfig dataclass used throughout the framework.

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
    from core.configuration_manager import ConfigurationManager

    config = ConfigurationManager.get_instance()
    app_cfg = config.app_config
    print(app_cfg.db_host)

Configuration Requirements:
    DB_HOST, DB_PORT, DB_SERVICE, DB_USER, DB_PASSWORD,
    LOG_LEVEL, INPUT_FOLDER, OUTPUT_FOLDER, REPORT_FOLDER, ARCHIVE_FOLDER
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Optional

from core.constants import Defaults, EnvKeys
from core.environment_manager import EnvironmentManager
from core.exception_manager import ConfigurationError
from core.logging_manager import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Typed configuration dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ApplicationConfig:
    """
    Immutable snapshot of the application configuration resolved at startup.

    All fields are typed; callers can rely on types without defensive casting.
    """

    # Application identity
    app_name: str
    app_env: str

    # Database
    db_host: str
    db_port: int
    db_service: str
    db_user: str
    db_password: str
    db_pool_size: int
    db_max_overflow: int
    db_pool_timeout: int
    db_pool_recycle: int
    db_connect_retries: int
    db_retry_delay: float

    # Logging
    log_level: str
    log_folder: Path
    log_json: bool

    # Folders
    base_folder: Path
    input_folder: Path
    output_folder: Path
    report_folder: Path
    archive_folder: Path

    # Derived
    db_dsn: str = field(init=False, compare=False)

    def __post_init__(self) -> None:
        # dataclass with frozen=True requires object.__setattr__ for derived fields
        object.__setattr__(
            self,
            "db_dsn",
            f"{self.db_host}:{self.db_port}/{self.db_service}",
        )

    def safe_summary(self) -> dict:
        """Return config as a dict with the password redacted for logging."""
        return {
            "app_name": self.app_name,
            "app_env": self.app_env,
            "db_host": self.db_host,
            "db_port": self.db_port,
            "db_service": self.db_service,
            "db_user": self.db_user,
            "db_password": "***REDACTED***",
            "db_dsn": self.db_dsn,
            "log_level": self.log_level,
            "log_folder": str(self.log_folder),
            "input_folder": str(self.input_folder),
            "output_folder": str(self.output_folder),
            "report_folder": str(self.report_folder),
            "archive_folder": str(self.archive_folder),
        }


# ---------------------------------------------------------------------------
# Singleton manager
# ---------------------------------------------------------------------------

class ConfigurationManager:
    """
    Thread-safe singleton that owns the lifecycle of ApplicationConfig.

    Usage pattern::

        cfg_mgr = ConfigurationManager.get_instance()
        config  = cfg_mgr.app_config

    The first call to ``get_instance()`` triggers ``_initialise()``.
    Subsequent calls return the cached instance.
    """

    _instance: ClassVar[Optional[ConfigurationManager]] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, env_file: str | Path | None = None) -> None:
        self._env_manager = EnvironmentManager(env_file=env_file)
        self._app_config: Optional[ApplicationConfig] = None

    # ------------------------------------------------------------------
    # Singleton accessor
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(
        cls, env_file: str | Path | None = None
    ) -> "ConfigurationManager":
        """
        Return the singleton ConfigurationManager, creating it on first call.

        Args:
            env_file: Path to the .env file.  Ignored on subsequent calls.

        Returns:
            The singleton ConfigurationManager instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:  # double-checked locking
                    instance = cls(env_file=env_file)
                    instance._initialise()
                    cls._instance = instance
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """
        Destroy the singleton.  Intended for use in unit tests only.
        Production code should never call this method.
        """
        with cls._lock:
            cls._instance = None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def app_config(self) -> ApplicationConfig:
        """The fully resolved ApplicationConfig snapshot."""
        if self._app_config is None:
            raise ConfigurationError(
                "ConfigurationManager has not been initialised.",
                error_code="CFG-005",
            )
        return self._app_config

    # ------------------------------------------------------------------
    # Private initialisation
    # ------------------------------------------------------------------

    def _initialise(self) -> None:
        """Load .env, validate, and build the ApplicationConfig dataclass."""
        self._env_manager.load_if_exists()
        self._validate()
        self._app_config = self._build_config()
        log.info(
            "Configuration initialised for app=%s env=%s",
            self._app_config.app_name,
            self._app_config.app_env,
        )

    def _validate(self) -> None:
        """Assert all mandatory environment variables are present."""
        required = [
            EnvKeys.DB_HOST,
            EnvKeys.DB_SERVICE,
            EnvKeys.DB_USER,
            EnvKeys.DB_PASSWORD,
        ]
        self._env_manager.assert_required(required)

    def _build_config(self) -> ApplicationConfig:
        """Construct ApplicationConfig from the current environment."""
        base_folder = Path(
            os.getenv(EnvKeys.BASE_FOLDER, Defaults.BASE_FOLDER)
        )

        return ApplicationConfig(
            # Application identity
            app_name=os.getenv(EnvKeys.APP_NAME, "erp_ai_app"),
            app_env=os.getenv(EnvKeys.APP_ENV, "development"),
            # Database
            db_host=self._env_manager.get_required(EnvKeys.DB_HOST),
            db_port=self._safe_int(
                os.getenv(EnvKeys.DB_PORT), Defaults.DB_PORT
            ),
            db_service=self._env_manager.get_required(EnvKeys.DB_SERVICE),
            db_user=self._env_manager.get_required(EnvKeys.DB_USER),
            db_password=self._env_manager.get_required(EnvKeys.DB_PASSWORD),
            db_pool_size=Defaults.DB_POOL_SIZE,
            db_max_overflow=Defaults.DB_MAX_OVERFLOW,
            db_pool_timeout=Defaults.DB_POOL_TIMEOUT,
            db_pool_recycle=Defaults.DB_POOL_RECYCLE,
            db_connect_retries=Defaults.DB_CONNECT_RETRIES,
            db_retry_delay=Defaults.DB_RETRY_DELAY,
            # Logging
            log_level=os.getenv(EnvKeys.LOG_LEVEL, Defaults.LOG_LEVEL).upper(),
            log_folder=base_folder / "logs",
            log_json=os.getenv("LOG_JSON", "false").lower() == "true",
            # Folders
            base_folder=base_folder,
            input_folder=Path(
                os.getenv(EnvKeys.INPUT_FOLDER, str(base_folder / "input"))
            ),
            output_folder=Path(
                os.getenv(EnvKeys.OUTPUT_FOLDER, str(base_folder / "output"))
            ),
            report_folder=Path(
                os.getenv(EnvKeys.REPORT_FOLDER, str(base_folder / "reports"))
            ),
            archive_folder=Path(
                os.getenv(EnvKeys.ARCHIVE_FOLDER, str(base_folder / "archive"))
            ),
        )

    @staticmethod
    def _safe_int(value: str | None, default: int) -> int:
        """Parse an integer from a string, returning *default* on failure."""
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default
