"""Batch CSV compatibility check endpoints."""

import csv
import json
import logging
from io import StringIO
from typing import Any, Dict, List

from flask import Blueprint, Response, jsonify, request

from src.api.helpers import serialize_issues, serialize_recommendations
from src.reasoning.compatibility_reasoner import CompatibilityReasoner

logger = logging.getLogger(__name__)

batch_bp = Blueprint("batch", __name__)

BATCH_REQUIRED_HEADERS = [
    "current_activegate_version",
    "target_activegate_version",
    "managed_cluster_version",
    "os_family",
    "os_version",
    "extensions",
]
BATCH_OUTPUT_HEADERS = [
    "compatibility_status",
    "compatibility_confidence",
    "compatibility_issues",
    "compatibility_warnings",
    "compatibility_recommendations",
    "row_error",
]
MAX_BATCH_ROWS = 5000

# Wired by the app factory.
_reasoner: CompatibilityReasoner = None  # type: ignore[assignment]


def _set_reasoner(reasoner: CompatibilityReasoner) -> None:
    """Inject the shared reasoner (called by the app factory)."""
    global _reasoner  # noqa: PLW0603
    _reasoner = reasoner


def _parse_extensions_cell(raw: str) -> List[Dict[str, str]]:
    """Parse the extensions JSON cell from a CSV row."""
    if not raw or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)  # type: ignore[reportUnknownVariableType]
    except json.JSONDecodeError as exc:  # type: ignore[reportArgumentType]
        raise ValueError(f"Invalid extensions JSON: {exc.msg}") from exc

    if not isinstance(parsed, dict):
        raise ValueError('Extensions must be a JSON object map like {"ext-id": "1.2.3"}')

    result: List[Dict[str, str]] = []
    for ext_id, ext_version in parsed.items():  # type: ignore[union-attr]
        if not str(ext_id).strip():
            raise ValueError("Extensions map contains an empty extension id")
        result.append({
            "id": str(ext_id).strip(),
            "version": "" if ext_version is None else str(ext_version).strip(),
        })
    return result


def _build_row_findings(row: Dict[str, str]) -> Dict[str, Any]:
    """Run the reasoner on a single CSV row and return findings."""
    current = (row.get("current_activegate_version") or "").strip()
    target = (row.get("target_activegate_version") or "").strip()

    if not current or not target:
        return {"row_error": "Missing required values for current_activegate_version and/or target_activegate_version"}

    raw_extensions = row.get("extensions") or ""
    try:
        extensions = _parse_extensions_cell(raw_extensions)
    except ValueError as exc:
        return {"row_error": str(exc)}

    result = _reasoner.check_upgrade_compatibility(  # type: ignore[union-attr]
        current_version=current,
        target_version=target,
        os_family=(row.get("os_family") or "").strip() or None,
        os_version=(row.get("os_version") or "").strip() or None,
        managed_cluster_version=(row.get("managed_cluster_version") or "").strip() or None,
        extensions=extensions,
        use_graph=_reasoner.graph_query is not None,  # type: ignore[union-attr]
    )

    return {
        "compatibility_status": result.status.value,
        "compatibility_confidence": f"{result.confidence:.2f}",
        "compatibility_issues": serialize_issues(result.issues),
        "compatibility_warnings": serialize_issues(result.warnings),
        "compatibility_recommendations": serialize_recommendations(result.recommendations),
    }


@batch_bp.route("/check/template", methods=["GET"])
def check_template_csv():
    """Download a CSV template for batch compatibility checks."""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=BATCH_REQUIRED_HEADERS)
    writer.writeheader()
    writer.writerow({
        "current_activegate_version": "1.330",
        "target_activegate_version": "1.335",
        "managed_cluster_version": "1.335",
        "os_family": "Red Hat Enterprise Linux",
        "os_version": "8",
        "extensions": '{"custom-ext":"2.0.0"}',
    })

    response = Response(output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = "attachment; filename=activegate-compatibility-template.csv"
    return response


@batch_bp.route("/check/batch-csv", methods=["POST"])
def batch_check_csv():
    """Process a CSV file and append compatibility findings columns per row."""
    upload = request.files.get("file")
    if upload is None:
        return jsonify({
            "error": "No file uploaded. Use multipart/form-data with field 'file'",
        }), 400

    try:
        csv_content = upload.read().decode("utf-8")
    except UnicodeDecodeError:
        return jsonify({"error": "Unable to decode file as UTF-8 CSV"}), 400

    reader = csv.DictReader(StringIO(csv_content))
    if not reader.fieldnames:
        return jsonify({"error": "Uploaded CSV has no header row"}), 400

    missing_headers = [h for h in BATCH_REQUIRED_HEADERS if h not in reader.fieldnames]
    if missing_headers:
        return jsonify({
            "error": "Missing required CSV headers",
            "missing_headers": missing_headers,
            "required_headers": BATCH_REQUIRED_HEADERS,
        }), 400

    input_headers = list(reader.fieldnames)  # type: ignore[union-attr]
    output_headers = input_headers + [h for h in BATCH_OUTPUT_HEADERS if h not in input_headers]

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=output_headers)
    writer.writeheader()

    row_count = 0
    for row in reader:
        row_count += 1
        if row_count > MAX_BATCH_ROWS:
            return jsonify({
                "error": f"CSV exceeds max supported rows ({MAX_BATCH_ROWS})",
                "max_rows": MAX_BATCH_ROWS,
            }), 400

        findings = _build_row_findings(row)
        row_out: Dict[str, Any] = dict(row)
        row_out.update(findings)
        writer.writerow(row_out)

    response = Response(output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = "attachment; filename=activegate-compatibility-with-findings.csv"
    return response
