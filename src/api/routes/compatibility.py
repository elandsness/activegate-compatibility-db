"""Compatibility check and chat endpoints."""

import logging
from typing import Dict, List

from flask import Blueprint, jsonify, request

from src.api.helpers import serialize_issues, serialize_recommendations
from src.reasoning.citation_generator import QueryProcessor
from src.reasoning.compatibility_reasoner import CompatibilityReasoner

logger = logging.getLogger(__name__)

# These will be wired by the app factory. Declared here to satisfy static checkers.
_reasoner: CompatibilityReasoner = None  # type: ignore[assignment]
_processor: QueryProcessor = None  # type: ignore[assignment]


def _set_components(reasoner: CompatibilityReasoner, processor: QueryProcessor) -> None:
    """Inject shared components (called by the app factory)."""
    global _reasoner, _processor  # noqa: PLW0603
    _reasoner = reasoner
    _processor = processor


compatibility_bp = Blueprint("compatibility", __name__)


@compatibility_bp.route("/chat", methods=["POST"])
def chat():
    """Chat endpoint for natural-language upgrade queries.

    Accepts:: {"message": "Can I upgrade from 1.330 to 1.335?", "context": {}}
    Returns:: {response, citations, status}
    """
    data = request.get_json() or {}
    message = data.get("message", "")
    context = data.get("context", {})

    if not message:
        return jsonify({"error": "No message provided"}), 400

    parsed = _processor.process_query(message, context=context)
    collected_context = parsed.get("context", {})

    if not parsed.get("ready_for_decision", False):
        return jsonify({
            "response": parsed.get("follow_up_prompt"),
            "citations": [],
            "status": "NEEDS_INFO",
            "missing_fields": parsed.get("missing_fields", []),
            "required_fields": _processor.REQUIRED_CONTEXT_FIELDS,
            "collected_context": collected_context,
        })

    current = collected_context.get("current_activegate_version")
    target = collected_context.get("target_activegate_version")
    os_family = collected_context.get("os_family")
    os_version = collected_context.get("os_version")
    managed_cluster_version = collected_context.get("managed_cluster_version")
    extensions = collected_context.get("extensions") or []

    result = _reasoner.check_upgrade_compatibility(
        current_version=current,
        target_version=target,
        os_family=os_family,
        os_version=os_version,
        managed_cluster_version=managed_cluster_version,
        extensions=extensions,
        use_graph=_reasoner.graph_query is not None,
    )

    response_text = _processor.format_result_for_display(result)

    return jsonify({
        "response": response_text,
        "versions_detected": {"current": current, "target": target},
        "citations": result.citations,
        "status": result.status.value if hasattr(result, "status") else "UNKNOWN",
        "confidence": result.confidence,
        "collected_context": collected_context,
        "missing_fields": [],
    })


@compatibility_bp.route("/check", methods=["POST"])
def check_compatibility():
    """Structured compatibility check endpoint.

    Accepts:: {"current": "1.330", "target": "1.335", ...}
    Returns:: CompatibilityResult as dict.
    """
    data = request.get_json() or {}
    current = data.get("current")
    target = data.get("target")

    if not current or not target:
        return jsonify({"error": "Current and target versions required"}), 400

    result = _reasoner.check_upgrade_compatibility(
        current_version=current,
        target_version=target,
        os_family=data.get("os_family"),
        os_version=data.get("os_version"),
        managed_cluster_version=data.get("managed_cluster_version"),
        extensions=data.get("extensions", []),
        use_graph=_reasoner.graph_query is not None,
    )

    return jsonify(result.to_dict())
