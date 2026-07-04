"""
Module Name: database_manager.py

Purpose:
    Enterprise database connection manager for Oracle databases.
    Provides engine creation, connection pooling, retry logic, session
    management, health validation, and context managers for safe resource
    handling. Supports both thick (OCI) and thin client modes of oracledb.

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
    python-dotenv

Usage:
    from core.database_manager import DatabaseManager

    db = DatabaseManager(
        host="myhost", port=1521, service="ORCL",
        user="myuser", password="secret"
    )
    db.initialise()

    # Direct connection
    with db.connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM DUAL")

    # SQLAlchemy session
    with db.session() as sess:
        result = sess.execute(text("SELECT SYSDATE FROM DUAL"))

Configuration Requirements:
    DB_HOST, DB_PORT, DB_SERVICE, DB_USER, DB_PASSWORD
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generator, Optional

import oracledb
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from core.constants import Defaults
from core.exception_manager import (
    DatabaseConnectionError,
    DatabaseQueryError,
)
from core.logging_manager import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration dataclass for the manager
# ---------------------------------------------------------------------------

@dataclass
class DatabaseConfig:
    """Connection parameters and pool settings for Oracle."""

    host: str
    service: str
    user: str
    password: str
    port: int = Defaults.DB_PORT
    pool_size: int = Defaults.DB_POOL_SIZE
    max_overflow: int = Defaults.DB_MAX_OVERFLOW
    pool_timeout: int = Defaults.DB_POOL_TIMEOUT
    pool_recycle: int = Defaults.DB_POOL_RECYCLE
    connect_retries: int = Defaults.DB_CONNECT_RETRIES
    retry_delay: float = Defaults.DB_RETRY_DELAY

    @property
    def dsn(self) -> str:
        return f"{self.host}:{self.port}/{self.service}"

    @property
    def connection_url(self) -> str:
        return (
            f"oracle+oracledb://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/?service_name={self.service}"
        )


# ---------------------------------------------------------------------------
# Main manager
# ---------------------------------------------------------------------------

class DatabaseManager:
    """
    Manages Oracle database connectivity for the aiframework.

    Responsibilities:
    - Oracle connection creation via oracledb (thin mode default)
    - SQLAlchemy engine and session factory creation
    - Connection pool management
    - Retry logic with exponential back-off
    - Context managers for connections and sessions
    - Health validation

    Example::

        db = DatabaseManager.from_config(app_config)
        db.initialise()

        with db.session() as sess:
            rows = sess.execute(text("SELECT * FROM HR.EMPLOYEES")).fetchall()
    """
        # ------------------------------------------------------------------
    # Backward Compatibility Wrappers (pytest support)
    # ------------------------------------------------------------------

    def _create_connection(self):
        """
        Legacy compatibility wrapper.
        """
        return self.connection()

    def _create_pool(self):
        """
        Legacy compatibility wrapper.
        """
        return self.get_engine()

    def check_health(self):
        """
        Legacy compatibility wrapper.
        """
        return self.test_connection()

    def __init__(self, config: DatabaseConfig) -> None:
        """
        Args:
            config: Fully populated DatabaseConfig instance.
        """
        self._config = config
        self._engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker] = None
        self._initialised: bool = False

    # ------------------------------------------------------------------
    # Alternate constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, app_config: object) -> "DatabaseManager":
        """
        Construct a DatabaseManager from an ApplicationConfig instance.

        Args:
            app_config: An ApplicationConfig (or compatible duck-typed object)
                        with ``db_host``, ``db_port``, ``db_service``,
                        ``db_user``, ``db_password`` attributes.

        Returns:
            A new, uninitialised DatabaseManager.
        """
        db_cfg = DatabaseConfig(
            host=app_config.db_host,               # type: ignore[attr-defined]
            port=app_config.db_port,               # type: ignore[attr-defined]
            service=app_config.db_service,         # type: ignore[attr-defined]
            user=app_config.db_user,               # type: ignore[attr-defined]
            password=app_config.db_password,       # type: ignore[attr-defined]
            pool_size=app_config.db_pool_size,     # type: ignore[attr-defined]
            max_overflow=app_config.db_max_overflow,  # type: ignore[attr-defined]
            pool_timeout=app_config.db_pool_timeout,  # type: ignore[attr-defined]
            pool_recycle=app_config.db_pool_recycle,  # type: ignore[attr-defined]
            connect_retries=app_config.db_connect_retries,  # type: ignore[attr-defined]
            retry_delay=app_config.db_retry_delay,  # type: ignore[attr-defined]
        )
        return cls(config=db_cfg)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialise(self, use_thin_mode: bool = True) -> None:
        """
        Bootstrap oracledb and create the SQLAlchemy engine.

        Args:
            use_thin_mode: Use oracledb thin client (no Oracle Instant Client
                           required).  Set to False for thick mode.

        Raises:
            DatabaseConnectionError: If the engine cannot connect after retries.
        """
        if self._initialised:
            log.debug("DatabaseManager already initialised – skipping.")
            return

        if use_thin_mode:
            oracledb.init_oracle_client()  # no-op in thin mode
            # Thin mode is the default in oracledb ≥ 1.0 — no extra call needed.

        self._engine = self._create_engine_with_retry()
        self._session_factory = sessionmaker(
            bind=self._engine, expire_on_commit=False
        )
        self._register_engine_events()
        self._initialised = True
        log.info(
            "DatabaseManager initialised. DSN=%s user=%s",
            self._config.dsn,
            self._config.user,
        )

    def dispose(self) -> None:
        """
        Dispose the connection pool and release all resources.

        Call this during application shutdown.
        """
        if self._engine:
            self._engine.dispose()
            log.info("Database engine disposed.")
        self._initialised = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_engine(self) -> Engine:
        """
        Return the underlying SQLAlchemy Engine.

        Returns:
            The active SQLAlchemy Engine.

        Raises:
            DatabaseConnectionError: If the manager has not been initialised.
        """
        self._assert_initialised()
        return self._engine  # type: ignore[return-value]

    def get_session(self) -> Session:
        """
        Open and return a new SQLAlchemy Session.

        The caller is responsible for committing/rolling back and closing
        the session.  Prefer the ``session()`` context manager instead.

        Returns:
            A new SQLAlchemy Session.
        """
        self._assert_initialised()
        return self._session_factory()  # type: ignore[misc]

    def test_connection(self) -> bool:
        """
        Execute a lightweight query to confirm database connectivity.

        Returns:
            ``True`` if the connection is healthy, ``False`` otherwise.
        """
        try:
            with self._engine.connect() as conn:  # type: ignore[union-attr]
                conn.execute(text("SELECT 1 FROM DUAL"))
            log.info("Database connection test passed.")
            return True
        except Exception as exc:
            log.warning("Database connection test failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Context managers
    # ------------------------------------------------------------------

    @contextmanager
    def connection(self) -> Generator[oracledb.Connection, None, None]:
        """
        Context manager that yields a raw oracledb connection.

        The connection is automatically closed on exit, regardless of
        whether an exception was raised.

        Yields:
            An active oracledb.Connection.

        Raises:
            DatabaseConnectionError: On connectivity failure.

        Example::

            with db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT SYSDATE FROM DUAL")
        """
        conn: Optional[oracledb.Connection] = None
        try:
            conn = oracledb.connect(
                user=self._config.user,
                password=self._config.password,
                dsn=self._config.dsn,
            )
            log.debug("Raw oracledb connection opened.")
            yield conn
        except oracledb.Error as exc:
            raise DatabaseConnectionError(
                f"Failed to obtain oracledb connection: {exc}",
                host=self._config.host,
                port=self._config.port,
            ) from exc
        finally:
            if conn:
                try:
                    conn.close()
                    log.debug("Raw oracledb connection closed.")
                except Exception:  # pylint: disable=broad-except
                    pass

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """
        Context manager that yields a SQLAlchemy Session with automatic
        commit/rollback handling.

        On normal exit the session is committed. On exception it is rolled
        back before the exception is re-raised.

        Yields:
            An active SQLAlchemy Session.

        Raises:
            DatabaseQueryError: Wraps any SQLAlchemy exception.

        Example::

            with db.session() as sess:
                sess.execute(text("INSERT INTO ..."))
        """
        self._assert_initialised()
        sess: Session = self._session_factory()  # type: ignore[misc]
        try:
            yield sess
            sess.commit()
            log.debug("Session committed.")
        except Exception as exc:
            sess.rollback()
            log.error("Session rolled back due to error: %s", exc)
            raise DatabaseQueryError(
                f"Session error: {exc}", error_code="DB-003"
            ) from exc
        finally:
            sess.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_engine_with_retry(self) -> Engine:
        """Create the SQLAlchemy engine, retrying on transient failures."""
        last_exc: Optional[Exception] = None

        for attempt in range(1, self._config.connect_retries + 1):
            try:
                engine = create_engine(
                    self._config.connection_url,
                    poolclass=QueuePool,
                    pool_size=self._config.pool_size,
                    max_overflow=self._config.max_overflow,
                    pool_timeout=self._config.pool_timeout,
                    pool_recycle=self._config.pool_recycle,
                    pool_pre_ping=True,   # validates connections before checkout
                    echo=False,
                )
                # Eagerly verify connectivity
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1 FROM DUAL"))

                log.info(
                    "Engine created successfully on attempt %d/%d",
                    attempt,
                    self._config.connect_retries,
                )
                return engine

            except Exception as exc:  # pylint: disable=broad-except
                last_exc = exc
                log.warning(
                    "Connection attempt %d/%d failed: %s",
                    attempt,
                    self._config.connect_retries,
                    exc,
                )
                if attempt < self._config.connect_retries:
                    delay = self._config.retry_delay * attempt  # linear back-off
                    log.info("Retrying in %.1f seconds…", delay)
                    time.sleep(delay)

        raise DatabaseConnectionError(
            f"Could not connect to Oracle after "
            f"{self._config.connect_retries} attempts. "
            f"Last error: {last_exc}",
            host=self._config.host,
            port=self._config.port,
        ) from last_exc

    def _assert_initialised(self) -> None:
        """Raise if the manager has not been initialised."""
        if not self._initialised or self._engine is None:
            raise DatabaseConnectionError(
                "DatabaseManager has not been initialised. "
                "Call initialise() first.",
                error_code="DB-004",
            )

    def _register_engine_events(self) -> None:
        """Attach SQLAlchemy engine-level event listeners for diagnostics."""

        @event.listens_for(self._engine, "connect")
        def on_connect(dbapi_conn, _connection_record) -> None:
            log.debug("New database connection established from pool.")

        @event.listens_for(self._engine, "checkout")
        def on_checkout(dbapi_conn, _connection_record, _connection_proxy) -> None:
            log.debug("Connection checked out from pool.")

        @event.listens_for(self._engine, "checkin")
        def on_checkin(dbapi_conn, _connection_record) -> None:
            log.debug("Connection returned to pool.")
