"""Flask API Backend for ActiveGate Compatibility Intelligence.

Entry point that wires shared components and registers route blueprints.
Run via ``python -m src.api.app`` or ``flask run`` with this module as app.
"""

import logging
import os

from flask import Flask
from flask_cors import CORS

from src.nlp.nlp_pipeline import NLPPipeline
from src.reasoning.citation_generator import QueryProcessor
from src.reasoning.compatibility_reasoner import CompatibilityReasoner
from src.storage.graph_connection import GraphConnection
from src.storage.graph_populater import GraphPopulator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _make_app() -> Flask:
    """Application factory — create, wire, and return the Flask app."""
    app = Flask(__name__)
    CORS(app)

    # --- Shared components ---------------------------------------------------
    graph_conn = GraphConnection(
        uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        user=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", "password"),
        database=os.environ.get("NEO4J_DATABASE", "neo4j"),
    )

    connected = graph_conn.connect()
    if connected:
        graph_query = GraphQuery(graph_conn)
        reasoner = CompatibilityReasoner(graph_query=graph_query)
        logger.info("Components initialised with live Neo4j connection.")
    else:
        reasoner = CompatibilityReasoner(graph_query=None)
        logger.warning("Neo4j unavailable at startup — running in offline mode.")

    _reasoner = reasoner  # local alias for the inject step below
    query_processor = QueryProcessor(reasoner)
    nlp_pipeline = NLPPipeline()

    # --- Inject shared components into route modules -------------------------
    from src.api.routes import compatibility, batch  # noqa: E402

    compatibility._set_components(_reasoner, query_processor)
    batch._set_reasoner(_reasoner)

    # --- Register route blueprints -------------------------------------------
    from src.api.routes import register_blueprints  # noqa: E402

    register_blueprints(app)

    return app


# Module-level application (for ``python -m`` entry point)
app = _make_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
