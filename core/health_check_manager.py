"""
Module Name: health_check_manager.py

Purpose:
    Performs comprehensive pre-flight health checks at application startup.
    Validates database connectivity, required tables, environment variables,
    folder structure, disk space, read/write permissions, configuration
    integrity, and log folder health. Produces a structured HTML/text report
    with PASS / WARNING / FAIL status for every check.

Author:
    Harish Mahanta

Version:
    1.0.0

Created Date:
    2026-06-18

Last Modified Date:
    2026-06-18

Dependencies:
    oracledb
    sqlalchemy

Usage:
    from core.health_check_manager import HealthCheckManager

    hcm = HealthCheckManager(
        config=app_config,
        db_manager=db_manager,
        folder_manager=folder_manager,
    )
    report = hcm.run_all()
    report.print_summary()
    report.raise_on_failure()   # raises HealthCheckError if any check FAILs

Configuration Requirements:
    All keys defined in ApplicationConfig must be resolvable.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional, Sequence

from core.constants import (
    Defaults,
    DATETIME_FORMAT,
    HealthStatus,
)
from core.exception_manager import HealthCheckError
from core.logging_manager import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    """Result of a single named health check."""

    name: str
    status: HealthStatus
    message: str
    detail: str = ""

    def is_pass(self) -> bool:
        return self.status == HealthStatus.PASS

    def is_warning(self) -> bool:
        return self.status == HealthStatus.WARNING

    def is_fail(self) -> bool:
        return self.status == HealthStatus.FAIL


@dataclass
class HealthReport:
    """
    Aggregated health-check report produced by HealthCheckManager.

    Attributes:
        app_name:   Name of the application under test.
        timestamp:  When the report was generated.
        results:    Ordered list of CheckResult entries.
    """

    app_name: str
    timestamp: datetime = field(default_factory=datetime.now)
    results: list[CheckResult] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def overall_status(self) -> HealthStatus:
        if any(r.is_fail() for r in self.results):
            return HealthStatus.FAIL
        if any(r.is_warning() for r in self.results):
            return HealthStatus.WARNING
        return HealthStatus.PASS

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.is_pass())

    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.results if r.is_warning())

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if r.is_fail())

    # ------------------------------------------------------------------
    # Output methods
    # ------------------------------------------------------------------

    def print_summary(self) -> None:
        """Print a formatted report to stdout."""
        separator = "=" * 70
        print(f"\n{separator}")
        print(f"  HEALTH CHECK REPORT  —  {self.app_name}")
        print(f"  Generated: {self.timestamp.strftime(DATETIME_FORMAT)}")
        print(separator)
        for result in self.results:
            icon = {"PASS": "✓", "WARNING": "⚠", "FAIL": "✗"}.get(
                result.status.value, "?"
            )
            print(
                f"  [{result.status.value:<7}] {icon}  {result.name:<40} {result.message}"
            )
            if result.detail:
                print(f"             ↳ {result.detail}")
        print(separator)
        print(
            f"  OVERALL: {self.overall_status.value}  "
            f"| PASS:{self.pass_count}  WARNING:{self.warning_count}  FAIL:{self.fail_count}"
        )
        print(f"{separator}\n")

    def to_dict(self) -> dict:
        """Serialise the report to a JSON-safe dictionary."""
        return {
            "app_name": self.app_name,
            "timestamp": self.timestamp.isoformat(),
            "overall_status": self.overall_status.value,
            "pass_count": self.pass_count,
            "warning_count": self.warning_count,
            "fail_count": self.fail_count,
            "checks": [
                {
                    "name": r.name,
                    "status": r.status.value,
                    "message": r.message,
                    "detail": r.detail,
                }
                for r in self.results
            ],
        }

    def raise_on_failure(self) -> None:
        """
        Raise HealthCheckError if any check produced a FAIL result.

        Raises:
            HealthCheckError: Listing all failed check names.
        """
        failed = [r.name for r in self.results if r.is_fail()]
        if failed:
            raise HealthCheckError(
                f"Health check failed. Failing checks: {failed}",
                details={"failed_checks": failed},
                error_code="HC-002",
            )


# ---------------------------------------------------------------------------
# Main manager
# ---------------------------------------------------------------------------

class HealthCheckManager:
    """
    Orchestrates all health checks for the aiframework application.

    Each check is isolated; a failure in one does not prevent subsequent
    checks from running, ensuring the report is always complete.
    """

    def __init__(
        self,
        config: object | None = None,
        db_manager: object | None = None,
        folder_manager: object | None = None,
        required_tables: Sequence[str] = (),
        required_env_keys: Sequence[str] = (),
        min_disk_free_gb: float = Defaults.MIN_DISK_FREE_GB,
    ) -> None:
        """
        Args:
            config:           ApplicationConfig (or compatible) instance.
            db_manager:       DatabaseManager instance (optional).
            folder_manager:   FolderManager instance (optional).
            required_tables:  List of Oracle table names to verify.
            required_env_keys: Additional env keys to validate beyond defaults.
            min_disk_free_gb: Minimum acceptable free disk space in GB.
        """
        self._config = config
        self._db_manager = db_manager
        self._folder_manager = folder_manager
        self._required_tables: Sequence[str] = required_tables
        self._required_env_keys: Sequence[str] = required_env_keys
        self._min_disk_free_gb = min_disk_free_gb

    # ------------------------------------------------------------------
    # Public wrapper methods (pytest compatibility)
    # ------------------------------------------------------------------

    def check_environment(self):
        """Public wrapper for environment validation."""
        return self._check_environment_variables()

    def check_database(self):
        """Public wrapper for database validation."""
        return self._check_database_connectivity()

    def check_folders(self):
        """Public wrapper for folder validation."""
        return {
            "structure": self._check_folder_structure(),
            "permissions": self._check_folder_permissions(),
        }

    def check_disk_space(self):
        """Public wrapper for disk validation."""
        return self._check_disk_space()

    def generate_report(self):
        """Public wrapper for complete report generation."""
        return self.run_all()
    
    def run(self):
        """
        Backward compatibility wrapper for legacy tests.
        """
        return self.run_all()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_all(self) -> HealthReport:
        """
        Execute every registered health check and return the consolidated
        HealthReport.

        Returns:
            HealthReport with results from all checks.
        """
        app_name = getattr(self._config, "app_name", "erp_ai_app")
        report = HealthReport(app_name=app_name)

        checks: list[Callable[[], CheckResult]] = [
            self._check_environment_variables,
            self._check_configuration_validation,
            self._check_log_folder,
            self._check_disk_space,
        ]

        if self._folder_manager is not None:
            checks.append(self._check_folder_structure)
            checks.append(self._check_folder_permissions)

        if self._db_manager is not None:
            checks.append(self._check_database_connectivity)
            if self._required_tables:
                checks.append(self._check_required_tables)

        for check_fn in checks:
            try:
                result = check_fn()
            except Exception as exc:  # pylint: disable=broad-except
                result = CheckResult(
                    name=check_fn.__name__.replace("_check_", "").replace("_", " ").title(),
                    status=HealthStatus.FAIL,
                    message="Check raised an unexpected exception.",
                    detail=str(exc),
                )
            report.results.append(result)
            log.info(
                "Health check [%s] %s: %s",
                result.status.value,
                result.name,
                result.message,
            )

        return report

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_environment_variables(self) -> CheckResult:
        """Verify that required environment variables are set."""
        from core.constants import EnvKeys

        mandatory = [
            EnvKeys.DB_HOST,
            EnvKeys.DB_SERVICE,
            EnvKeys.DB_USER,
            EnvKeys.DB_PASSWORD,
        ]
        all_keys = list(mandatory) + list(self._required_env_keys)
        missing = [k for k in all_keys if not os.getenv(k, "").strip()]

        if missing:
            return CheckResult(
                name="Environment Variables",
                status=HealthStatus.FAIL,
                message=f"{len(missing)} required variable(s) missing.",
                detail=f"Missing: {missing}",
            )
        return CheckResult(
            name="Environment Variables",
            status=HealthStatus.PASS,
            message=f"All {len(all_keys)} required variables present.",
        )

    def _check_configuration_validation(self) -> CheckResult:
        """Validate that ApplicationConfig has non-empty mandatory fields."""
        issues: list[str] = []
        for attr in ("db_host", "db_service", "db_user", "db_password"):
            val = getattr(self._config, attr, "")
            if not str(val).strip():
                issues.append(attr)

        if issues:
            return CheckResult(
                name="Configuration Validation",
                status=HealthStatus.FAIL,
                message=f"{len(issues)} config field(s) are empty.",
                detail=f"Empty fields: {issues}",
            )
        return CheckResult(
            name="Configuration Validation",
            status=HealthStatus.PASS,
            message="All mandatory configuration fields are populated.",
        )

    def _check_log_folder(self) -> CheckResult:
        """Verify that the log folder exists and is writable."""
        log_folder = getattr(self._config, "log_folder", None)
        if log_folder is None:
            return CheckResult(
                name="Log Folder",
                status=HealthStatus.WARNING,
                message="log_folder not defined in config.",
            )

        import tempfile
        from pathlib import Path

        log_path = Path(log_folder)
        if not log_path.exists():
            return CheckResult(
                name="Log Folder",
                status=HealthStatus.WARNING,
                message="Log folder does not exist (will be created at startup).",
                detail=str(log_path),
            )
        try:
            with tempfile.NamedTemporaryFile(dir=log_path, delete=True):
                pass
            return CheckResult(
                name="Log Folder",
                status=HealthStatus.PASS,
                message="Log folder exists and is writable.",
                detail=str(log_path),
            )
        except OSError as exc:
            return CheckResult(
                name="Log Folder",
                status=HealthStatus.FAIL,
                message="Log folder is not writable.",
                detail=str(exc),
            )

    def _check_disk_space(self) -> CheckResult:
        """Verify that sufficient free disk space is available."""
        usage = shutil.disk_usage(".")
        free_gb = usage.free / (1024 ** 3)

        if free_gb < self._min_disk_free_gb:
            return CheckResult(
                name="Disk Space",
                status=HealthStatus.FAIL,
                message=f"Low disk space: {free_gb:.2f} GB free.",
                detail=f"Minimum required: {self._min_disk_free_gb} GB",
            )
        if free_gb < self._min_disk_free_gb * 2:
            return CheckResult(
                name="Disk Space",
                status=HealthStatus.WARNING,
                message=f"Disk space is low: {free_gb:.2f} GB free.",
                detail=f"Consider freeing space; threshold: {self._min_disk_free_gb} GB",
            )
        return CheckResult(
            name="Disk Space",
            status=HealthStatus.PASS,
            message=f"{free_gb:.2f} GB free disk space.",
        )

    def _check_folder_structure(self) -> CheckResult:
        """Verify all standard folders exist."""
        results = self._folder_manager.validate_all()  # type: ignore[union-attr]
        missing = [str(r.folder) for r in results if not r.exists]

        if missing:
            return CheckResult(
                name="Folder Structure",
                status=HealthStatus.WARNING,
                message=f"{len(missing)} folder(s) missing (will be created).",
                detail=f"Missing: {missing}",
            )
        return CheckResult(
            name="Folder Structure",
            status=HealthStatus.PASS,
            message=f"All {len(results)} standard folders exist.",
        )

    def _check_folder_permissions(self) -> CheckResult:
        """Verify all standard folders are readable and writable."""
        results = self._folder_manager.validate_all()  # type: ignore[union-attr]
        not_writable = [str(r.folder) for r in results if r.exists and not r.writable]

        if not_writable:
            return CheckResult(
                name="Folder Permissions",
                status=HealthStatus.FAIL,
                message=f"{len(not_writable)} folder(s) not writable.",
                detail=f"Not writable: {not_writable}",
            )
        return CheckResult(
            name="Folder Permissions",
            status=HealthStatus.PASS,
            message="All existing folders are readable and writable.",
        )

    def _check_database_connectivity(self) -> CheckResult:
        """Attempt a live database connection."""
        try:
            healthy = self._db_manager.test_connection()  # type: ignore[union-attr]
            if healthy:
                return CheckResult(
                    name="Database Connectivity",
                    status=HealthStatus.PASS,
                    message="Database connection successful.",
                    detail=f"DSN: {getattr(self._config, 'db_dsn', 'unknown')}",
                )
            return CheckResult(
                name="Database Connectivity",
                status=HealthStatus.FAIL,
                message="test_connection() returned False.",
            )
        except Exception as exc:  # pylint: disable=broad-except
            return CheckResult(
                name="Database Connectivity",
                status=HealthStatus.FAIL,
                message="Database connection failed.",
                detail=str(exc),
            )

    def _check_required_tables(self) -> CheckResult:
        """Verify that all required Oracle tables exist in the schema."""
        missing: list[str] = []
        try:
            from sqlalchemy import text, inspect

            engine = self._db_manager.get_engine()  # type: ignore[union-attr]
            inspector = inspect(engine)
            existing_tables = {t.upper() for t in inspector.get_table_names()}

            for table in self._required_tables:
                if table.upper() not in existing_tables:
                    missing.append(table)

        except Exception as exc:  # pylint: disable=broad-except
            return CheckResult(
                name="Required Tables",
                status=HealthStatus.FAIL,
                message="Could not inspect database tables.",
                detail=str(exc),
            )

        if missing:
            return CheckResult(
                name="Required Tables",
                status=HealthStatus.FAIL,
                message=f"{len(missing)} required table(s) not found.",
                detail=f"Missing: {missing}",
            )
        return CheckResult(
            name="Required Tables",
            status=HealthStatus.PASS,
            message=f"All {len(self._required_tables)} required table(s) found.",
        )
