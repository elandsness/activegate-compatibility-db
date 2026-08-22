"""Ingest rate limiter — shared singleton used by the ingestion blueprint."""

import threading
import time


class IngestRateLimiter:
    """Simple in-memory rate limiter to prevent rapid repeated ingest calls."""

    def __init__(self, min_interval_seconds: float = 30.0) -> None:
        self._min_interval = min_interval_seconds
        self._last_time: float = 0.0
        self._lock = threading.Lock()
        self._ingesting = False

    def allow(self) -> bool:
        """Return True if an ingest is allowed right now."""
        with self._lock:
            if self._ingesting:
                return False
            elapsed = time.monotonic() - self._last_time
            if elapsed < self._min_interval:
                return False
            return True

    def start(self) -> None:
        """Mark that an ingest is in progress."""
        with self._lock:
            self._ingesting = True

    def finish(self) -> None:
        """Mark that an ingest has completed and reset the timer."""
        with self._lock:
            self._last_time = time.monotonic()
            self._ingesting = False


# Singleton — imported by routes/ingestion.py
_ingest_limiter = IngestRateLimiter(min_interval_seconds=30.0)
