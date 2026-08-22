"""Admin endpoints (destructive operations — should be guarded)."""

import logging

from flask import Blueprint, jsonify

from src.api.helpers import make_graph_connection

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin/clear-graph", methods=["POST"])
def clear_graph():
    """Clear all Neo4j graph data. Use for resetting ingestion state."""
    graph_conn = make_graph_connection()
    try:
        graph_conn.connect()
        graph_conn.clear_database()
        return jsonify({"status": "success", "message": "Neo4j graph cleared"})
    except Exception as exc:
        logger.error("Clear-graph error: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500
