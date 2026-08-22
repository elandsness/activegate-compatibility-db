"""Data query endpoints (versions, relationships, graph visualization)."""

import logging
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request

from src.api.helpers import (
    make_graph_connection,
    normalize_graph_value,
    pick_node_key,
    relationship_status,
    serialize_issues,
    serialize_recommendations,
    status_color,
)

logger = logging.getLogger(__name__)

data_bp = Blueprint("data", __name__)


@data_bp.route("/data/versions", methods=["GET"])
def get_versions():
    """Get all ActiveGate versions in the database."""
    graph_conn = make_graph_connection()
    try:
        graph_conn.connect()
        result = graph_conn.execute("""
            MATCH (ag:ActiveGateVersion)
            WHERE coalesce(ag.is_release, false) = true
            RETURN ag.version AS version ORDER BY ag.version
        """)
        return jsonify({"versions": [r["version"] for r in result]})
    except Exception as exc:
        return jsonify({"error": str(exc), "versions": []}), 500


@data_bp.route("/data/managed-versions", methods=["GET"])
def get_managed_versions():
    """Get all Managed cluster versions in the database."""
    graph_conn = make_graph_connection()
    try:
        graph_conn.connect()
        result = graph_conn.execute("""
            MATCH (mc:ManagedClusterVersion)
            WHERE coalesce(mc.is_release, false) = true
            RETURN mc.version AS version ORDER BY mc.version
        """)
        return jsonify({"versions": [r["version"] for r in result]})
    except Exception as exc:
        return jsonify({"error": str(exc), "versions": []}), 500


@data_bp.route("/data/relationships", methods=["GET"])
def get_relationships():
    """Get relationship statistics."""
    graph_conn = make_graph_connection()
    try:
        graph_conn.connect()
        result = graph_conn.execute("""
            MATCH (a)-[r]->(b)
            RETURN type(r) AS relationship, count(*) AS count
        """)
        return jsonify({
            "relationships": [{"type": r["relationship"], "count": r["count"]} for r in result],
        })
    except Exception as exc:
        return jsonify({"error": str(exc), "relationships": []}), 500


@data_bp.route("/data/hub-summary", methods=["GET"])
def get_hub_summary():
    """Get managed Hub ingestion coverage and health summary."""
    graph_conn = make_graph_connection()
    try:
        graph_conn.connect()
        from src.storage.graph_populater import GraphPopulator
        summary = GraphPopulator(graph_conn).get_hub_coverage_summary()
        return jsonify(summary)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def _build_graph_rows(rows, limit: int) -> Dict[str, Any]:
    """Build nodes/edges payload from raw graph query rows."""
    nodes_by_id: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []

    for idx, row in enumerate(rows):
        source_labels = row.get("source_labels") or []
        target_labels = row.get("target_labels") or []
        source_props = row.get("source_props") or {}
        target_props = row.get("target_props") or {}

        source_type = source_labels[0] if source_labels else "Node"
        target_type = target_labels[0] if target_labels else "Node"

        source_id = f"{source_type}:{pick_node_key(source_labels, source_props)}"
        target_id = f"{target_type}:{pick_node_key(target_labels, target_props)}"

        if source_id not in nodes_by_id:
            nodes_by_id[source_id] = {
                "id": source_id,
                "label": pick_node_key(source_labels, source_props),
                "type": source_type,
                "properties": {k: normalize_graph_value(v) for k, v in source_props.items()},
            }

        if target_id not in nodes_by_id:
            nodes_by_id[target_id] = {
                "id": target_id,
                "label": pick_node_key(target_labels, target_props),
                "type": target_type,
                "properties": {k: normalize_graph_value(v) for k, v in target_props.items()},
            }

        rel_type = row.get("relationship_type") or "RELATED_TO"
        rel_props = row.get("relationship_props") or {}
        status = relationship_status(rel_type)

        edges.append({
            "id": f"e{idx}",
            "source": source_id,
            "target": target_id,
            "relationship": rel_type,
            "status": status,
            "color": status_color(status),
            "confidence": normalize_graph_value(rel_props.get("confidence")),
            "verified": normalize_graph_value(rel_props.get("verified")),
        })

    status_counts: Dict[str, int] = {
        "compatible": 0, "questionable": 0,
        "incompatible": 0, "unknown": 0,
    }
    for edge in edges:
        status_counts[edge["status"]] = status_counts.get(edge["status"], 0) + 1

    return {
        "nodes": list(nodes_by_id.values()),
        "edges": edges,
        "status_counts": status_counts,
    }


@data_bp.route("/data/graph", methods=["GET"])
def get_graph_data():
    """Return node/edge payload for interactive graph rendering."""
    graph_conn = make_graph_connection()
    try:
        graph_conn.connect()

        activegate_version = request.args.get("activegate_version")
        raw_limit = request.args.get("limit", "500")
        try:
            limit = max(50, min(int(raw_limit), 1200))
        except ValueError:
            limit = 500

        activegate_limit = max(10, min(limit // 2, 250))

        rows = graph_conn.execute("""
            MATCH (ag:ActiveGateVersion)
            WHERE coalesce(ag.is_release, false) = true
              AND ($activegate_version IS NULL OR ag.version = $activegate_version)
            WITH ag ORDER BY ag.version DESC LIMIT $activegate_limit
            MATCH (ag)-[r]-(other)
            WHERE (
              other:ManagedClusterVersion OR other:OSVersion OR other:Extension OR
              other:HubItem OR other:HubItemRelease OR other:Module OR other:Setting OR
              other:ActiveGateVersion
            )
            WITH DISTINCT r, startNode(r) AS src, endNode(r) AS dst
            RETURN labels(src) AS source_labels, properties(src) AS source_props,
                   labels(dst) AS target_labels, properties(dst) AS target_props,
                   type(r) AS relationship_type, properties(r) AS relationship_props
            LIMIT $edge_limit
        """, {
            "activegate_version": activegate_version,
            "activegate_limit": activegate_limit,
            "edge_limit": limit,
        })

        payload = _build_graph_rows(rows, limit)
        payload["filters"] = {"activegate_version": activegate_version, "limit": limit}
        return jsonify(payload)
    except Exception as exc:
        return jsonify({"error": str(exc), "nodes": [], "edges": []}), 500


@data_bp.route("/visualize", methods=["GET"])
def visualize():
    """Get text-graph visualization data."""
    from src.storage.graph_visualizer import GraphVisualizer
    try:
        visualizer = GraphVisualizer()
        data = visualizer.get_graph_data(limit=20)
        return jsonify({"visualization": visualizer.to_text_diagram(data)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
