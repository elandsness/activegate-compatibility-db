"""Auth helpers for the API layer.

``auth_required()`` guards routes that perform destructive or sensitive
operations.  It checks ``ADMIN_SECRET_HEADER`` (default: ``X-Admin-Secret``)
against ``ADMIN_API_KEY`` env var.  If the env var is unset, auth is
bypassed (development mode).
"""

import functools
import os

from flask import jsonify, request


def auth_required(fn):  # type: ignore[func-returns-value]
    """Decorate a Flask view to require admin authentication."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
        secret_header = os.environ.get(
            "ADMIN_SECRET_HEADER", "X-Admin-Secret"
        )
        expected_key = os.environ.get("ADMIN_API_KEY", "")

        # If no key configured, allow (development mode).
        if not expected_key:
            return fn(*args, **kwargs)

        actual = request.headers.get(secret_header, "")
        if actual != expected_key:
            return jsonify({"error": "Unauthorized"}), 401

        return fn(*args, **kwargs)

    return wrapper  # type: ignore[no-any-return]
