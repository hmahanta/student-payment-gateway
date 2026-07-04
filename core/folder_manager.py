"""
Module Name: folder_manager.py

Purpose:
    Creates and validates the standard directory structure required by every
    project built on aiframework. Ensures that all folders exist and
    are readable/writable before any processing begins.

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
    from core.folder_manager import FolderManager

    fm = FolderManager(base_path="/opt/myapp")
    fm.create_all()
    fm.assert_writable()

Configuration Requirements:
    BASE_FOLDER  - Root directory for all sub-folders (default: current directory)
"""

from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from core.constants import FolderNames, HealthStatus
from core.exception_manager import ApplicationError
from core.logging_manager import get_logger

log = get_logger(__name__)


@dataclass
class FolderValidationResult:
    """Result of a single folder validation check."""

    folder: Path
    exists: bool
    readable: bool
    writable: bool
    status: HealthStatus

    def is_healthy(self) -> bool:
        return self.status == HealthStatus.PASS


@dataclass
class FolderManager:
    """
    Manages the standard folder structure for an aiframework application.

    The manager creates all required directories and exposes validation
    helpers used by the HealthCheckManager at startup.

    Attributes:
        base_path: Root directory under which all sub-folders are created.
        folders:   Mapping of folder-name enum → resolved Path.
    """

    base_path: Path
    folders: dict[str, Path] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.base_path = Path(self.base_path)
        self._register_standard_folders()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_all(self) -> None:
        """
        Create every registered folder (including parents) if it does not
        already exist.

        Raises:
            ApplicationError: If a folder cannot be created due to
                              permission or OS errors.
        """
        for name, path in self.folders.items():
            try:
                path.mkdir(parents=True, exist_ok=True)
                log.debug("Folder ready: %s", path)
            except OSError as exc:
                raise ApplicationError(
                    f"Cannot create folder '{name}' at {path}: {exc}",
                    error_code="FOLDER-001",
                ) from exc
        log.info(
            "All %d standard folders are ready under %s",
            len(self.folders),
            self.base_path,
        )

    def create_folder(self, name: str, relative_path: str | None = None) -> Path:
        """
        Register and create a single additional folder.

        Args:
            name:          Logical name for the folder.
            relative_path: Path relative to ``base_path``.  When ``None``
                           *name* itself is used as the relative path.

        Returns:
            The resolved absolute Path of the created folder.
        """
        path = self.base_path / (relative_path or name)
        path.mkdir(parents=True, exist_ok=True)
        self.folders[name] = path
        log.debug("Custom folder registered and created: %s", path)
        return path

    def validate_all(self) -> list[FolderValidationResult]:
        """
        Validate all registered folders for existence and read/write access.

        Returns:
            List of FolderValidationResult for every registered folder.
        """
        results: list[FolderValidationResult] = []
        for name, path in self.folders.items():
            result = self._validate_single(path)
            results.append(result)
            log.debug(
                "Folder check [%s] %s → %s",
                result.status.value,
                name,
                path,
            )
        return results

    def assert_writable(self, folders: Sequence[str] | None = None) -> None:
        """
        Assert that specified (or all) folders are writable.

        Args:
            folders: Subset of folder keys to check.  When ``None`` all
                     registered folders are checked.

        Raises:
            ApplicationError: If any folder is not writable.
        """
        targets = (
            {k: self.folders[k] for k in folders if k in self.folders}
            if folders
            else self.folders
        )
        not_writable = [
            str(path)
            for path in targets.values()
            if not self._is_writable(path)
        ]
        if not_writable:
            raise ApplicationError(
                f"The following folders are not writable: {not_writable}",
                error_code="FOLDER-002",
            )

    def get(self, name: str) -> Path:
        """
        Retrieve the Path for a registered folder.

        Args:
            name: Logical folder name.

        Returns:
            Resolved Path.

        Raises:
            KeyError: If *name* is not registered.
        """
        if name not in self.folders:
            raise KeyError(
                f"Folder '{name}' is not registered. "
                f"Available: {list(self.folders.keys())}"
            )
        return self.folders[name]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _register_standard_folders(self) -> None:
        """Populate the ``folders`` dict from the FolderNames enum."""
        for folder_name in FolderNames:
            self.folders[folder_name.value] = self.base_path / folder_name.value

    def _validate_single(self, path: Path) -> FolderValidationResult:
        """Validate a single folder and return a result object."""
        exists = path.exists() and path.is_dir()
        readable = os.access(path, os.R_OK) if exists else False
        writable = self._is_writable(path) if exists else False

        if exists and readable and writable:
            status = HealthStatus.PASS
        elif exists and readable:
            status = HealthStatus.WARNING
        else:
            status = HealthStatus.FAIL

        return FolderValidationResult(
            folder=path,
            exists=exists,
            readable=readable,
            writable=writable,
            status=status,
        )

    @staticmethod
    def _is_writable(path: Path) -> bool:
        """
        Verify write access by attempting to create and delete a temp file.
        ``os.access`` alone is unreliable on some networked file systems.
        """
        if not path.exists():
            return False
        try:
            with tempfile.NamedTemporaryFile(dir=path, delete=True):
                return True
        except OSError:
            return False
