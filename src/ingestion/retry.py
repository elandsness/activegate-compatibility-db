"""Retry helpers for HTTP requests in scrapers.

Provides a ``@retry`` decorator with exponential back-off and jitter,
plus a thin wrapper around ``requests.request`` that auto-retries on
transient errors (connection reset, 5xx).
"""

from __future__ import annotations

import functools
import logging
import random
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Default retry budget
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BASE_DELAY = 1.0  # seconds


def retry(
    max_retries: int = _DEFAULT_MAX_RETRIES,
    base_delay: float = _DEFAULT_BASE_DELAY,
    jitter: bool = True,
    retryable_statuses: tuple[int, ...] = (429, 500, 502, 503, 504),
):
    """Decorate a function to retry on transient errors.

    Example::

        @retry(max_retries=5, base_delay=2.0)
        def fetch_page(url): ...
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return fn(*args, **kwargs)  # type: ignore[no-any-return]
                except (requests.RequestException, OSError) as exc:  # noqa: F821
                    last_exc = exc
                    if attempt == max_retries:
                        break
                    delay = base_delay * (2**attempt) + (random.uniform(0, 1) if jitter else 0)
                    logger.warning(
                        "%s failed on attempt %d/%d: %s — retrying in %.1fs",
                        fn.__name__, attempt + 1, max_retries + 1, exc, delay,
                    )
                    time.sleep(delay)
            raise RuntimeError(f"{fn.__name__} failed after {max_retries + 1} attempts") from last_exc

        return wrapper

    return decorator


def get_with_retry(
    session: Any,
    url: str,
    *,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    timeout: tuple[int, int] | int = (10, 30),
    base_delay: float = _DEFAULT_BASE_DELAY,
) -> Any:
    """Fetch a URL with retries; returns the response object."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", base_delay * 2))
                logger.warning("Rate-limited (429) on %s — waiting %ds", url[:60], retry_after)
                time.sleep(retry_after)
                continue
            resp.raise_for_status()
            return resp
        except (requests.RequestException, OSError) as exc:  # noqa: F821
            last_exc = exc
            if attempt == max_retries:
                break
            delay = base_delay * (2**attempt) + random.uniform(0, 1)
            logger.warning("GET %s failed on attempt %d: %s — retrying in %.1fs", url[:60], attempt + 1, exc, delay)
            time.sleep(delay)
    raise RuntimeError(f"GET {url} failed after {max_retries + 1} attempts") from last_exc
