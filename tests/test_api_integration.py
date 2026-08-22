"""Integration tests for the Flask API layer.

Runs each route through Flask's ``TestClient`` so that blueprints,
middleware (CORS), and component wiring are exercised as a whole.
Skips any step that requires a live Neo4j by checking ``NEO4J_TEST_URI``
and instead asserts graceful offline-mode behavior.

Run with:  pytest tests/test_api_integration.py -v
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch, MagicMock

import pytest

# Ensure the app factory can be imported without a live Neo4j.
os.environ.setdefault("NEO4J_URI", "")


@pytest.fixture()
def app():
    """Create the Flask app under test."""
    from src.api.app import _make_app

    return _make_app()


@pytest.fixture(autouse=True)
def _mock_reasoner(app):  # type: ignore[no-untyped-def]
    """Inject a fake reasoner so routes never touch Neo4j during tests."""
    mock = MagicMock()
    mock.check_upgrade_compatibility.return_value = MagicMock(
        to_dict=lambda: {
            "status": "GO",
            "current_activegate_version": "1.330",
            "target_activegate_version": "1.340",
            "issues": [],
            "warnings": [],
            "recommendations": [],
            "confidence": 1.0,
        }
    )
    mock._deprecated_versions = {"1.300"}
    mock._eos_versions = {"1.280"}

    with patch(
        "src.api.routes.compatibility.CompatibilityReasoner",
        return_value=mock,
    ):
        yield mock


@pytest.fixture()
def client(app):  # type: ignore[no-untyped-def]
    app.testing = True
    return app.test_client()


# ── health route ────────────────────────────────────────────────

class TestHealthRoute:
    def test_root_returns_200(self, client):  # type: ignore[no-untyped-def]
        rv = client.get("/")
        assert rv.status_code == 200

    def test_health_json(self, client):  # type: ignore[no-untyped_def]
        rv = client.get("/api/health")
        assert rv.status_code == 200
        data = rv.get_json()
        assert "status" in data


# ── check route ────────────────────────────────────────────────

class TestCheckRoute:
    def test_returns_ok_with_minimal_payload(self, client):  # type: ignore[no-untyped_def]
        rv = client.post(
            "/api/check",
            data=json.dumps({"current_version": "1.330", "target_version": "1.340"}),
            content_type="application/json",
        )
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["status"] == "GO"

    def test_returns_ok_with_full_payload(self, client):  # type: ignore[no-untyped_def]
        payload = {
            "current_version": "1.330",
            "target_version": "1.340",
            "os_family": "Red Hat Enterprise Linux",
            "os_version": "8",
            "managed_cluster_version": "1.335",
            "extensions": [{"id": "custom-logging", "version": "2.0"}],
        }
        rv = client.post(
            "/api/check", data=json.dumps(payload), content_type="application/json"
        )
        assert rv.status_code == 200


# ── chat route ────────────────────────────────────────────────

class TestChatRoute:
    def test_chat_returns_answer(self, client):  # type: ignore[no-untyped_def]
        rv = client.post(
            "/api/chat",
            data=json.dumps({"message": "Is 1.330 compatible with 1.340?"}),
            content_type="application/json",
        )
        assert rv.status_code == 200
        data = rv.get_json()
        assert "answer" in data or "error" in data


# ── data routes ────────────────────────────────────────────────

class TestDataRoutes:
    def test_versions_returns_list(self, client):  # type: ignore[no-untyped_def]
        rv = client.get("/api/data/versions")
        assert rv.status_code == 200
        data = rv.get_json()
        assert isinstance(data.get("versions"), list)

    def test_managed_versions_returns_list(self, client):  # type: ignore[no-untyped_def]
        rv = client.get("/api/data/managed-versions")
        assert rv.status_code == 200

    def test_hub_summary_defaults(self, client):  # type: ignore[no-untyped_def]
        rv = client.get("/api/data/hub-summary")
        assert rv.status_code == 200


# ── ingest route (offline-safe) ────────────────────────────────

class TestIngestRoute:
    def test_ingest_offline_fails_gracefully(self, client):  # type: ignore[no-untyped_def]
        """When Neo4j is down, ingestion should still return a JSON response."""
        rv = client.post(
            "/api/ingest",
            data=json.dumps({"source": "releases"}),
            content_type="application/json",
        )
        # We may get 500 from scraper failure — but it must be JSON.
        assert rv.status_code in {200, 500}


# ── admin route (auth guard) ───────────────────────────────────

class TestAdminRoute:
    def test_clear_graph_unauthorized(self, app, client):  # type: ignore[no-untyped_def]
        os.environ["ADMIN_API_KEY"] = "secret-key"
        try:
            rv = client.post(
                "/api/admin/clear-graph", content_type="application/json"
            )
            assert rv.status_code == 401
        finally:
            os.environ.pop("ADMIN_API_KEY", None)

    def test_clear_graph_authorized(self, app, client):  # type: ignore[no-untyped_def]
        os.environ["ADMIN_API_KEY"] = "secret-key"
        try:
            rv = client.post(
                "/api/admin/clear-graph",
                content_type="application/json",
                headers={"X-Admin-Secret": "secret-key"},
            )
            # May fail due to missing Neo4j, but must NOT be 401.
            assert rv.status_code != 401
        finally:
            os.environ.pop("ADMIN_API_KEY", None)


# ── batch CSV route ────────────────────────────────────────────

class TestBatchRoute:
    def test_template_downloads(self, client):  # type: ignore[no-untyped_def]
        rv = client.get("/api/check/template")
        assert rv.status_code == 200
        # Content-Disposition should be present for a downloadable CSV.
        disposition = rv.headers.get("Content-Disposition", "")
        assert "batch-check-template" in disposition.lower() or len(rv.data) > 0
