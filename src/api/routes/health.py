"""Health and info endpoints."""

from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/")
def index():
    """Root endpoint with API documentation and endpoint list."""
    return jsonify({
        "service": "ActiveGate Compatibility API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/api/health",
            "chat": "/api/chat (POST)",
            "check": "/api/check (POST)",
            "batch_check": "/api/check/batch-csv (POST)",
            "check_template": "/api/check/template (GET)",
            "ingest": "/api/ingest (POST)",
            "versions": "/api/data/versions",
            "relationships": "/api/data/relationships",
            "visualize": "/api/visualize",
        },
        "web_ui": "Port 3000",
    })


@health_bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "ActiveGate Compatibility API",
    })
