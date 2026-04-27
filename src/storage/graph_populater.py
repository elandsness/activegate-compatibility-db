import logging
from typing import List, Dict, Optional
from datetime import datetime
from src.storage.graph_connection import GraphConnection
from src.nlp.nlp_pipeline import ExtractedFact

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GraphPopulator:
    """Populates Neo4j graph with extracted compatibility facts."""
    
    def __init__(self, graph_conn: GraphConnection):
        """
        Initialize graph populator.
        
        Args:
            graph_conn: GraphConnection instance
        """
        self.graph_conn = graph_conn
    
    def populate_from_facts(self, facts: List[ExtractedFact]) -> int:
        """
        Populate graph from a list of extracted facts.
        
        Args:
            facts: List of ExtractedFact objects to insert
        
        Returns:
            Count of facts inserted
        """
        inserted = 0
        for fact in facts:
            try:
                if self.insert_fact(fact):
                    inserted += 1
            except Exception as e:
                logger.error(f"Error inserting fact: {e}")
        
        logger.info(f"Inserted {inserted} facts into graph")
        return inserted
    
    def insert_fact(self, fact: ExtractedFact) -> bool:
        """Insert a single fact into the graph."""
        try:
            if fact.fact_type == 'compatibility_statement':
                return self._insert_compatibility_statement(fact)
            elif fact.fact_type == 'upgrade_path':
                return self._insert_upgrade_path(fact)
            else:
                logger.warning(f"Unknown fact type: {fact.fact_type}")
                return False
        except Exception as e:
            logger.error(f"Error inserting fact: {e}")
            return False
    
    def _insert_compatibility_statement(self, fact: ExtractedFact) -> bool:
        """Insert a compatibility statement fact."""
        # Extract component type from predicate (e.g., 'activegate_compatible' -> 'activegate', 'compatible')
        parts = fact.predicate.split('_')
        if len(parts) < 2:
            return False
        
        component = parts[0]
        relationship_type = '_'.join(parts[1:]).upper()
        
        # Create nodes and relationships based on component type
        if component == 'activegate':
            return self._insert_activegate_compatibility(
                fact, relationship_type
            )
        elif component == 'os':
            return self._insert_os_compatibility(
                fact, relationship_type
            )
        elif component == 'extension':
            return self._insert_extension_compatibility(
                fact, relationship_type
            )
        elif component == 'managed_cluster':
            return self._insert_managed_cluster_compatibility(
                fact, relationship_type
            )
        
        return False
    
    def _insert_activegate_compatibility(self, fact: ExtractedFact, relationship_type: str) -> bool:
        """Insert ActiveGate compatibility information."""
        query = """
        MERGE (ag:ActiveGateVersion {version: $version})
        SET ag.last_seen = datetime()
        WITH ag
        MERGE (source:Source {url: $source_url})
        SET source.title = $source_title, source.timestamp = datetime()
        WITH ag, source
        CREATE (provenance:Provenance {
            source_url: $source_url,
            confidence: $confidence,
            extracted_at: datetime(),
            raw_text: $raw_text
        })
        CREATE (ag)-[:HAS_PROVENANCE]->(provenance)
        CREATE (provenance)-[:FROM_SOURCE]->(source)
        RETURN ag, provenance
        """
        
        try:
            result = self.graph_conn.execute(query, {
                'version': fact.subject,
                'source_url': fact.source_url,
                'source_title': 'Release Notes',
                'confidence': fact.confidence,
                'raw_text': fact.source_text
            })
            return result is not None
        except Exception as e:
            logger.error(f"Error inserting ActiveGate compatibility: {e}")
            return False
    
    def _insert_os_compatibility(self, fact: ExtractedFact, relationship_type: str) -> bool:
        """Insert OS compatibility information."""
        query = """
        MERGE (os:OSVersion {os_name: 'Unknown', version: $version})
        SET os.last_seen = datetime()
        WITH os
        MERGE (source:Source {url: $source_url})
        WITH os, source
        CREATE (provenance:Provenance {
            source_url: $source_url,
            confidence: $confidence,
            extracted_at: datetime()
        })
        CREATE (os)-[:HAS_PROVENANCE]->(provenance)
        RETURN os, provenance
        """
        
        try:
            result = self.graph_conn.execute(query, {
                'version': fact.subject,
                'source_url': fact.source_url,
                'confidence': fact.confidence
            })
            return result is not None
        except Exception as e:
            logger.error(f"Error inserting OS compatibility: {e}")
            return False
    
    def _insert_extension_compatibility(self, fact: ExtractedFact, relationship_type: str) -> bool:
        """Insert extension compatibility information."""
        query = """
        MERGE (ext:Extension {id: $extension_id, version: $version})
        SET ext.last_seen = datetime()
        WITH ext
        MERGE (source:Source {url: $source_url})
        WITH ext, source
        CREATE (provenance:Provenance {
            source_url: $source_url,
            confidence: $confidence,
            extracted_at: datetime()
        })
        CREATE (ext)-[:HAS_PROVENANCE]->(provenance)
        RETURN ext, provenance
        """
        
        try:
            result = self.graph_conn.execute(query, {
                'extension_id': fact.object or 'unknown',
                'version': fact.subject,
                'source_url': fact.source_url,
                'confidence': fact.confidence
            })
            return result is not None
        except Exception as e:
            logger.error(f"Error inserting extension compatibility: {e}")
            return False
    
    def _insert_managed_cluster_compatibility(self, fact: ExtractedFact, relationship_type: str) -> bool:
        """Insert Managed cluster compatibility information."""
        query = """
        MERGE (mc:ManagedClusterVersion {version: $version})
        SET mc.last_seen = datetime()
        WITH mc
        MERGE (source:Source {url: $source_url})
        WITH mc, source
        CREATE (provenance:Provenance {
            source_url: $source_url,
            confidence: $confidence,
            extracted_at: datetime()
        })
        CREATE (mc)-[:HAS_PROVENANCE]->(provenance)
        RETURN mc, provenance
        """
        
        try:
            result = self.graph_conn.execute(query, {
                'version': fact.subject,
                'source_url': fact.source_url,
                'confidence': fact.confidence
            })
            return result is not None
        except Exception as e:
            logger.error(f"Error inserting Managed cluster compatibility: {e}")
            return False
    
    def _insert_upgrade_path(self, fact: ExtractedFact) -> bool:
        """Insert an upgrade path (from version X to version Y)."""
        query = """
        MERGE (from_ag:ActiveGateVersion {version: $from_version})
        MERGE (to_ag:ActiveGateVersion {version: $to_version})
        MERGE (from_ag)-[r:UPGRADEABLE_TO {confidence: $confidence}]->(to_ag)
        SET r.source_url = $source_url, r.raw_text = $raw_text, r.created_at = datetime()
        RETURN from_ag, to_ag, r
        """
        
        try:
            result = self.graph_conn.execute(query, {
                'from_version': fact.subject,
                'to_version': fact.object,
                'confidence': fact.confidence,
                'source_url': fact.source_url,
                'raw_text': fact.source_text
            })
            return result is not None
        except Exception as e:
            logger.error(f"Error inserting upgrade path: {e}")
            return False
    
    def create_compatibility_relationship(self, 
                                        from_version: str, 
                                        to_version: str,
                                        relationship_type: str,
                                        confidence: float,
                                        source_url: str) -> bool:
        """
        Create a compatibility relationship between two versions.
        
        Args:
            from_version: Source version (e.g., ActiveGate 1.335)
            to_version: Target version (e.g., Managed 1.335)
            relationship_type: Type of relationship (COMPATIBLE_WITH, REQUIRES, etc.)
            confidence: Confidence score (0.0-1.0)
            source_url: Source URL for provenance
        """
        query = f"""
        MATCH (from:ActiveGateVersion {{version: $from_version}})
        MATCH (to:ManagedClusterVersion {{version: $to_version}})
        MERGE (from)-[r:{relationship_type} {{confidence: $confidence}}]->(to)
        SET r.source_url = $source_url, r.created_at = datetime()
        RETURN r
        """
        
        try:
            result = self.graph_conn.execute(query, {
                'from_version': from_version,
                'to_version': to_version,
                'confidence': confidence,
                'source_url': source_url
            })
            return result is not None
        except Exception as e:
            logger.error(f"Error creating compatibility relationship: {e}")
            return False
