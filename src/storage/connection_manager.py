"""Shared Neo4j connection manager with pool lifecycle and factory helper.

The singleton ``graph_mgr`` is the single source of truth for Neo4j access
across the API, CLI, and graph visualizer.  It lazily creates a driver on
first use (or when explicitly told to connect), so processes without a
Neo4j backend can still run without errors.

Usage outside the API:
    from src.storage.connection_manager import graph_mgr

    graph_mgr.connect()              # explicit, blocks until ready
    session = graph_mgr.session()    # context manager for a single run

In Flask (app factory):
    mgr = make_manager_for_app(app)  # attaches to app.extensions for shutdown
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING, Generator, Optional

from flask import Flask, current_app

if TYPE_CHECKING:
    pass

try:
    from neo4j import Driver, GraphDatabase  # type: ignore[import-untyped]
except ImportError:
    GraphDatabase = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ── Singleton ----------------------------------------------------------------

_graph_instance: Optional["ConnectionManager"] = None
_lock = threading.Lock()


def get_manager() -> "ConnectionManager":
    """Return the global singleton, creating it on first call."""
    global _graph_instance
    if _graph_instance is None:
        with _lock:
            if _graph_instance is None:
                _graph_instance = ConnectionManager()
    return _graph_instance


def make_manager_for_app(app: Flask) -> "ConnectionManager":
    """Create an app-scoped manager and hook it to the shutdown lifecycle."""
    # Use the singleton if it exists, otherwise create a new one
    mgr = get_manager()

    # Initialize with env vars if this is a new instance
    if not mgr._uri:
        mgr._uri = os.environ.get("NEO4J_URI", "")
        mgr._user = os.environ.get("NEO4J_USER", "neo4j")
        mgr._password = os.environ.get("NEO4J_PASSWORD", "")
        mgr._database = os.environ.get("NEO4J_DATABASE", "neo4j")

    app.extensions["neo4j_manager"] = mgr  # type: ignore[attr-defined]
    app.teardown_appcontext(_shutdown_mgr)
    return mgr


def _shutdown_mgr(exc: Optional[BaseException]) -> None:
    """Called at end of each request cycle.

    NOTE: We deliberately do NOT disconnect the shared singleton manager here.
    The connection is process-scoped and will be cleaned up when the process exits.
    Disconnecting per-request breaks subsequent requests that need the connection.
    """
    pass


# ── ConnectionManager --------------------------------------------------------

class ConnectionManager:
    """Thin wrapper around a neo4j.Driver with pool lifecycle."""

    def __init__(
        self,
        uri: str = "",
        user: str = "neo4j",
        password: str = "",
        database: str = "neo4j",
    ) -> None:
        self._uri = uri
        self._user = user
        self._password = password
        self._database = database
        self._driver: Optional[Driver] = None

    @property
    def driver(self):
        """Expose internal driver for code that checks `graph_conn.driver`."""
        return self._driver

    @property
    def is_connected(self) -> bool:
        return self._driver is not None and GraphDatabase is not None

    # -- connection ---------------------------------------------------------

    def connect(self, timeout_s: int = 10) -> bool:
        """Establish the underlying driver. Returns True on success."""
        if not self._uri:
            logger.warning("Neo4j disabled: no URI configured")
            return False
        if not GraphDatabase:
            logger.warning("Neo4j disabled: neo4j package not installed")
            return False
        logger.info("Connecting to Neo4j at %s (user=%s)", self._uri, self._user)
        try:
            self._driver = GraphDatabase.driver(
                self._uri, auth=(self._user, self._password), max_connection_lifetime=timeout_s
            )
            with self._driver.session(database=self._database) as sesh:
                sesh.run("RETURN 1")
            logger.info("Connected to Neo4j at %s", self._uri)
            return True
        except Exception as exc:
            logger.error("Neo4j connect failed: %s", exc, exc_info=True)
            return False

    def disconnect(self) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Disconnected from Neo4j")

    # -- session helpers ----------------------------------------------------

    @contextmanager
    def session(self) -> Generator[object, None, None]:
        """Yield a neo4j Session (context manager)."""
        if not self._driver:
            raise RuntimeError("Neo4j not connected — call connect() first")
        with self._driver.session(database=self._database) as sesh:
            yield sesh

    def query(self, cypher: str, params: dict | None = None):
        """Run a Cypher statement and return the full result list."""
        if not self._driver:
            raise RuntimeError("Neo4j not connected")
        with self.session() as sesh:
            result = sesh.run(cypher, params or {})
            return list(result)

    # Backwards-compat alias for GraphQuery / old code that expects .execute()
    execute = query

    # -- index helpers ------------------------------------------------------

    def ensure_indexes(self) -> None:
        """Create indexes used by the ingestion pipeline (idempotent)."""
        idx_defs = [
            ("ActiveGateVersion", "version"),
            ("ManagedClusterVersion", "version"),
            ("OSVersion", "os_name, version"),
            ("Extension", "id, version"),
        ]
        for label, key in idx_defs:
            name = f"idx_{label.lower()}_{key.replace(' ', '_')}"
            self.query(
                f"CREATE INDEX {name} IF NOT EXISTS FOR (n:{label}) ON (n.{key})",
            )

    # -- stats --------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return node and relationship counts for monitoring."""
        labels = ["ActiveGateVersion", "ManagedClusterVersion", "OSVersion", "Extension"]
        stats: dict[str, int] = {}
        for label in labels:
            rows = self.query(f"MATCH (n:{label}) RETURN count(n) as c")
            stats[f"{label}_count"] = rows[0]["c"] if rows else 0
        rows = self.query("MATCH ()-[r]->() RETURN count(r) as c")
        stats["relationships_count"] = rows[0]["c"] if rows else 0
        return stats
