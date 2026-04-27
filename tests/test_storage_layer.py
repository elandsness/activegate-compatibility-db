#!/usr/bin/env python3
"""
Test script for storage layer.
Tests graph connection, population, and querying with mocked Neo4j connection.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.storage.graph_connection import GraphConnection
from src.storage.graph_populater import GraphPopulator
from src.storage.graph_query import GraphQuery
from src.nlp.nlp_pipeline import ExtractedFact


class MockGraphConnection(GraphConnection):
    """Mock GraphConnection for testing without a real Neo4j instance."""
    
    def __init__(self):
        super().__init__("bolt://localhost:7687", "neo4j", "password")
        self.queries_executed = []
        self.mock_data = {}
    
    def connect(self) -> bool:
        """Return True for mock connection."""
        print("Mock connection established")
        return True
    
    def disconnect(self):
        """Mock disconnect."""
        print("Mock connection closed")
    
    def execute(self, query: str, parameters: dict = None) -> list:
        """Log query and return mock data."""
        self.queries_executed.append({'query': query, 'parameters': parameters})
        
        # Return mock results based on query type
        if 'ActiveGateVersion' in query and 'version' in (parameters or {}):
            return [{'ag': {'version': parameters['version']}}]
        elif 'MATCH' in query:
            return [{'r': None}]
        else:
            return []
    
    def create_indexes(self):
        """Mock index creation."""
        print("Mock indexes created")
    
    def get_stats(self) -> dict:
        """Return mock statistics."""
        return {
            'ActiveGateVersion_count': 5,
            'ManagedClusterVersion_count': 5,
            'OSVersion_count': 8,
            'Extension_count': 20,
            'relationships_count': 50
        }


def test_graph_connection():
    """Test graph connection management."""
    print("=" * 60)
    print("Testing Graph Connection")
    print("=" * 60)
    
    conn = MockGraphConnection()
    
    # Test connection
    assert conn.connect(), "Connection should succeed"
    print("✓ Connection established")
    
    # Test statistics
    stats = conn.get_stats()
    print(f"✓ Database stats: {stats}")
    
    # Test disconnect
    conn.disconnect()
    print("✓ Connection closed")


def test_graph_population():
    """Test graph population from extracted facts."""
    print("\n" + "=" * 60)
    print("Testing Graph Population")
    print("=" * 60)
    
    conn = MockGraphConnection()
    conn.connect()
    
    populator = GraphPopulator(conn)
    
    # Create sample facts
    facts = [
        ExtractedFact(
            fact_type='compatibility_statement',
            subject='1.335',
            predicate='activegate_compatible',
            object_val='activegate',
            confidence=0.9,
            source_url='https://docs.dynatrace.com/managed/whats-new/managed/sprint-335',
            source_text='ActiveGate 1.335 supports Managed 1.335'
        ),
        ExtractedFact(
            fact_type='upgrade_path',
            subject='1.330',
            predicate='upgradeable_to',
            object_val='1.335',
            confidence=0.95,
            source_url='https://docs.dynatrace.com/managed/whats-new/managed/sprint-335',
            source_text='Upgrade from 1.330 to 1.335'
        ),
    ]
    
    # Populate from facts
    inserted = populator.populate_from_facts(facts)
    print(f"✓ Inserted {inserted} facts")
    
    # Check executed queries
    print(f"✓ Executed {len(conn.queries_executed)} queries")
    for i, query_info in enumerate(conn.queries_executed):
        print(f"  Query {i+1}: {query_info['query'][:60]}...")


def test_graph_query():
    """Test graph querying and compatibility checks."""
    print("\n" + "=" * 60)
    print("Testing Graph Queries")
    print("=" * 60)
    
    conn = MockGraphConnection()
    conn.connect()
    
    query_engine = GraphQuery(conn)
    
    # Test compatibility check
    print("\nChecking ActiveGate 1.335 compatibility with Managed 1.335...")
    result = query_engine.check_activegate_compatibility(
        activegate_version='1.335',
        managed_version='1.335',
        os_family='linux',
        extensions=['ext1', 'ext2']
    )
    
    print(f"✓ Status: {result['status']}")
    print(f"  Confidence: {result['confidence']:.2f}")
    if result['issues']:
        print(f"  Issues: {result['issues']}")
    if result['warnings']:
        print(f"  Warnings: {result['warnings']}")
    if result['recommendations']:
        print(f"  Recommendations: {result['recommendations']}")
    
    # Test compatible versions lookup
    print("\nGetting compatible ActiveGate versions for Managed 1.335...")
    compatible = query_engine.get_compatible_activegate_versions('1.335')
    print(f"✓ Compatible versions: {compatible}")
    
    # Test OS compatibility
    print("\nChecking OS compatibility...")
    os_compat = query_engine.check_os_compatibility('1.335', 'linux')
    print(f"✓ Linux compatible: {os_compat['compatible']}")
    
    # Test extension compatibility
    print("\nChecking extension compatibility...")
    ext_compat = query_engine.check_extensions_compatibility(
        '1.335',
        ['monitoring-ext', 'logging-ext']
    )
    print(f"✓ Failed extensions: {ext_compat['failed']}")
    print(f"✓ Warnings: {ext_compat['warnings']}")
    
    # Test upgrade paths
    print("\nFinding upgrade paths...")
    paths = query_engine.get_upgrade_paths('1.330', '1.335')
    print(f"✓ Found {len(paths)} upgrade paths")
    
    # Test entity details
    print("\nGetting entity details...")
    details = query_engine.get_entity_details('activegate', '1.335')
    print(f"✓ Entity details: {details}")


def test_integration():
    """Test integration of ingestion -> NLP -> storage pipeline."""
    print("\n" + "=" * 60)
    print("Testing Integration: Ingestion -> NLP -> Storage")
    print("=" * 60)
    
    from src.nlp.nlp_pipeline import NLPPipeline, FactConverter
    
    # Sample release note
    sample_text = """
    ActiveGate 1.335 Release Notes
    
    Compatibility: ActiveGate 1.335 is compatible with Dynatrace Managed 1.335 and later.
    
    Supported OS: Windows Server 2019, 2022, Linux (CentOS 8.x, RHEL 8.x, 9.x, Ubuntu 20.04, 22.04)
    
    Upgrade: Existing users can upgrade from version 1.330 to 1.335.
    
    Deprecations: Version 1.300 and earlier are deprecated.
    """
    
    # Process with NLP pipeline
    nlp_pipeline = NLPPipeline()
    extraction_result = nlp_pipeline.process_document(
        text=sample_text,
        source_url='https://docs.dynatrace.com/managed/whats-new/managed/sprint-335',
        source_title='What\'s new in Dynatrace ActiveGate 1.335'
    )
    
    print(f"✓ Extracted {len(extraction_result.compatibility_statements)} compatibility statements")
    print(f"✓ Extracted {len(extraction_result.version_pairs)} version pairs")
    
    # Convert to facts
    facts = FactConverter.convert_to_facts(extraction_result)
    print(f"✓ Converted to {len(facts)} facts")
    
    # Populate graph
    conn = MockGraphConnection()
    conn.connect()
    
    populator = GraphPopulator(conn)
    inserted = populator.populate_from_facts(facts)
    print(f"✓ Inserted {inserted} facts into graph")
    
    # Query graph
    query_engine = GraphQuery(conn)
    compatibility = query_engine.check_activegate_compatibility('1.335', '1.335')
    print(f"✓ Compatibility status: {compatibility['status']}")


if __name__ == '__main__':
    test_graph_connection()
    test_graph_population()
    test_graph_query()
    test_integration()
    
    print("\n" + "=" * 60)
    print("All storage tests completed successfully!")
    print("=" * 60)
