"""
Module Name: application_context.py

Purpose:
    ApplicationContext is the top-level Dependency Injection container for
    the aiframework. It wires together all core infrastructure objects
    (config, logging, folders, database, health checks) and exposes them
    through a single, lazily-initialised façade.

    Importing projects call ApplicationContext.bootstrap() once at startup
    and then access services through the returned singleton.

Author:
    Harish Mahanta

Version:
    1.0.0

Created Date:
    2026-06-18

Last Modified Date:
    2026-06-18

Dependencies:
    All aiframework.core modules

Usage:
    from core.application_context import ApplicationContext

    ctx = ApplicationContext.bootstrap(env_file=".env", init_db=True)
    ctx.health_report.print_summary()
    ctx.health_report.raise_on_failure()

    with ctx.db.session() as sess:
        ...

Configuration Requirements:
    See env.template for the full list of required variables.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import ClassVar, Optional, Sequence

from core.configuration_manager import (
    ApplicationConfig,
    ConfigurationManager,
)
from core.database_manager import DatabaseManager
from core.folder_manager import FolderManager
from core.health_check_manager import HealthCheckManager, HealthReport
from core.logging_manager import configure_root_logger, get_logger

log = get_logger(__name__)


class ApplicationContext:
    """
    Central DI container that bootstraps and owns every infrastructure service.

    Attributes:
        config:        The resolved ApplicationConfig.
        db:            DatabaseManager (None if ``init_db=False``).
        folders:       FolderManager with all standard directories.
        health_report: HealthReport generated during bootstrap.
    """

    _instance: ClassVar[Optional[ApplicationContext]] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(
        self,
        config: ApplicationConfig,
        db: Optional[DatabaseManager],
        folders: FolderManager,
        health_report: HealthReport,
    ) -> None:
        self.config = config
        self.db = db
        self.folders = folders
        self.health_report = health_report

    # ------------------------------------------------------------------
    # Singleton bootstrap
    # ------------------------------------------------------------------

    @classmethod
    def bootstrap(
        cls,
        env_file: str | Path | None = None,
        init_db: bool = True,
        use_thin_db_mode: bool = True,
        required_tables: Sequence[str] = (),
        required_env_keys: Sequence[str] = (),
        run_health_checks: bool = True,
    ) -> "ApplicationContext":
        """
        Bootstrap the entire framework and return the singleton context.

        This method is idempotent: subsequent calls return the cached
        instance without re-running initialisation.

        Args:
            env_file:          Path to the .env file.
            init_db:           Whether to initialise the database connection.
            use_thin_db_mode:  Use oracledb thin client (no OCI required).
            required_tables:   Oracle tables that must exist for health check.
            required_env_keys: Extra env keys to validate in health check.
            run_health_checks: Whether to run and attach the HealthReport.

        Returns:
            The singleton ApplicationContext.
        """
        if cls._instance is not None:
            return cls._instance

        with cls._lock:
            if cls._instance is not None:
                return cls._instance

            configure_root_logger()
            log.info("Bootstrapping aiframework ApplicationContext…")

            # 1. Configuration
            cfg_manager = ConfigurationManager.get_instance(env_file=env_file)
            config = cfg_manager.app_config
            log.info("Configuration loaded: %s", config.safe_summary())

            # 2. Folders
            folders = FolderManager(base_path=config.base_folder)
            folders.create_all()

            # 3. Database
            db: Optional[DatabaseManager] = None
            if init_db:
                db = DatabaseManager.from_config(config)
                db.initialise(use_thin_mode=use_thin_db_mode)

            # 4. Health checks
            health_report: HealthReport
            if run_health_checks:
                hcm = HealthCheckManager(
                    config=config,
                    db_manager=db,
                    folder_manager=folders,
                    required_tables=required_tables,
                    required_env_keys=required_env_keys,
                )
                health_report = hcm.run_all()
                health_report.print_summary()
            else:
                from core.health_check_manager import HealthReport as HR
                health_report = HR(app_name=config.app_name)

            ctx = cls(
                config=config,
                db=db,
                folders=folders,
                health_report=health_report,
            )
            cls._instance = ctx
            log.info("ApplicationContext bootstrap complete.")
            return ctx

    @classmethod
    def reset(cls) -> None:
        """
        Destroy the singleton and dispose the database engine.

        Intended for use in unit tests only.
        """
        with cls._lock:
            if cls._instance and cls._instance.db:
                cls._instance.db.dispose()
            cls._instance = None
            ConfigurationManager.reset()
