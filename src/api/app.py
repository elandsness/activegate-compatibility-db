"""
Flask API Backend for ActiveGate Compatibility Intelligence
Provides REST endpoints for chat, compatibility checks, and data management.
"""

import os
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from src.reasoning.compatibility_reasoner import CompatibilityReasoner
from src.reasoning.citation_generator import QueryProcessor
from src.nlp.nlp_pipeline import NLPPipeline
from src.storage.graph_connection import GraphConnection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)


@app.route('/')
def index():
    """Root endpoint with API info."""
    return jsonify({
        'service': 'ActiveGate Compatibility API',
        'version': '1.0.0',
        'endpoints': {
            'health': '/api/health',
            'chat': '/api/chat (POST)',
            'check': '/api/check (POST)',
            'ingest': '/api/ingest (POST)',
            'versions': '/api/data/versions',
            'relationships': '/api/data/relationships',
            'visualize': '/api/visualize'
        },
        'web_ui': 'Port 3000'
    })


def get_graph_connection():
    """Get Neo4j connection from environment variables."""
    return GraphConnection(
        uri=os.environ.get('NEO4J_URI', 'bolt://localhost:7687'),
        user=os.environ.get('NEO4J_USER', 'neo4j'),
        password=os.environ.get('NEO4J_PASSWORD', 'password'),
        database=os.environ.get('NEO4J_DATABASE', 'neo4j')
    )


def get_reasoner():
    """Get or create CompatibilityReasoner instance."""
    try:
        graph_conn = get_graph_connection()
        graph_conn.connect()
        return CompatibilityReasoner(graph_query=None)
    except Exception as e:
        logger.warning(f"Could not connect to Neo4j: {e}. Using offline mode.")
        return CompatibilityReasoner()


# Initialize components
reasoner = get_reasoner()
query_processor = QueryProcessor(reasoner)
nlp_pipeline = NLPPipeline()


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'ActiveGate Compatibility API'
    })


@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Chat endpoint for natural language queries.
    Accepts: {"message": "Can I upgrade from 1.330 to 1.335?"}
    Returns: {"response": "...", "citations": [...], "status": "GO|NO_GO"}
    """
    data = request.get_json()
    message = data.get('message', '')
    
    if not message:
        return jsonify({'error': 'No message provided'}), 400
    
    # Process the query
    parsed = query_processor.process_query(message)
    versions = parsed.get('versions_found', [])
    
    if len(versions) >= 2:
        current = versions[0]
        target = versions[1]
    elif len(versions) == 1:
        current = '1.330'  # Default
        target = versions[0]
    else:
        return jsonify({
            'response': 'Could not detect version in query. Please use format: "Can I upgrade from X to Y?"',
            'citations': [],
            'status': 'UNKNOWN'
        })
    
    # Run compatibility check
    result = reasoner.check_upgrade_compatibility(
        current_version=current,
        target_version=target
    )
    
    # Format response
    response_text = query_processor.format_result_for_display(result)
    
    return jsonify({
        'response': response_text,
        'versions_detected': {'current': current, 'target': target},
        'citations': result.citations,
        'status': result.status.value if hasattr(result, 'status') else 'UNKNOWN',
        'confidence': result.confidence
    })


@app.route('/api/check', methods=['POST'])
def check_compatibility():
    """
    Structured compatibility check endpoint.
    Accepts: {"current": "1.330", "target": "1.335", "os_family": "linux", ...}
    Returns: Compatibility result with issues and recommendations.
    """
    data = request.get_json()
    
    current = data.get('current')
    target = data.get('target')
    os_family = data.get('os_family')
    os_version = data.get('os_version')
    managed = data.get('managed_cluster_version')
    extensions = data.get('extensions', [])
    
    if not current or not target:
        return jsonify({'error': 'Current and target versions required'}), 400
    
    # Run compatibility check
    result = reasoner.check_upgrade_compatibility(
        current_version=current,
        target_version=target,
        os_family=os_family,
        os_version=os_version,
        managed_cluster_version=managed,
        extensions=extensions
    )
    
    return jsonify(result.to_dict())


@app.route('/api/ingest', methods=['POST'])
def ingest_data():
    """
    Ingest data from URL or text.
    Accepts: {"url": "...", "text": "..."}
    Returns: {"status": "success", "facts_extracted": N}
    """
    data = request.get_json()
    url = data.get('url')
    text = data.get('text')
    
    if not text and not url:
        return jsonify({'error': 'Either url or text required'}), 400
    
    if text:
        # Process text directly
        result = nlp_pipeline.process_document(
            text=text,
            source_url=url or '',
            source_title=data.get('title', 'Manual Input')
        )
    else:
        # TODO: Implement URL fetching
        return jsonify({'error': 'URL ingestion not yet implemented'}), 501
    
    return jsonify({
        'status': 'success',
        'facts_extracted': len(result.compatibility_statements),
        'versions_found': len(result.entities.get('versions', [])),
        'statements_found': len(result.compatibility_statements)
    })


@app.route('/api/data/versions', methods=['GET'])
def get_versions():
    """Get all ActiveGate versions in the database."""
    try:
        graph_conn = get_graph_connection()
        graph_conn.connect()
        
        query = "MATCH (ag:ActiveGateVersion) RETURN ag.version as version ORDER BY ag.version"
        result = graph_conn.execute(query)
        
        versions = [record['version'] for record in result]
        return jsonify({'versions': versions})
    except Exception as e:
        return jsonify({'error': str(e), 'versions': []}), 500


@app.route('/api/data/relationships', methods=['GET'])
def get_relationships():
    """Get relationship statistics."""
    try:
        graph_conn = get_graph_connection()
        graph_conn.connect()
        
        # Count relationships by type
        query = """
        MATCH (a)-[r]->(b)
        RETURN type(r) as relationship, count(*) as count
        """
        result = graph_conn.execute(query)
        
        relationships = [{'type': r['relationship'], 'count': r['count']} for r in result]
        return jsonify({'relationships': relationships})
    except Exception as e:
        return jsonify({'error': str(e), 'relationships': []}), 500


@app.route('/api/visualize', methods=['GET'])
def visualize():
    """Get graph visualization data."""
    from src.storage.graph_visualizer import GraphVisualizer
    
    try:
        visualizer = GraphVisualizer()
        data = visualizer.get_graph_data(limit=20)
        text_output = visualizer.to_text_diagram(data)
        return jsonify({'visualization': text_output})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=port, debug=debug)