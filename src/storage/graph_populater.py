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
        if not self.graph_conn.connect():
            logger.error("GraphPopulator could not connect to Neo4j during initialization")
    
    def populate_from_facts(self, facts: List[ExtractedFact]) -> int:
        """
        Populate graph from a list of extracted facts.

        Args:
            facts: List of ExtractedFact objects to insert

        Returns:
            Count of facts inserted
        """
        if not self.graph_conn.driver:
            if not self.graph_conn.connect():
                logger.error("Failed to connect to Neo4j: cannot insert facts")
                return 0

        inserted = 0
        for fact in facts:
            try:
                if self.insert_fact(fact):
                    inserted += 1
            except Exception as e:
                logger.error(f"Error inserting fact: {e}")
        
        logger.info(f"Inserted {inserted} facts into graph")
        return inserted
    
    def ensure_activegate_release_node(self, version: str, title: str, source_url: str) -> bool:
        """Ensure an ActiveGate release node exists in Neo4j."""
        if not self.graph_conn.driver:
            if not self.graph_conn.connect():
                logger.error("Failed to connect to Neo4j: cannot ensure release node")
                return False

        query = """
        MERGE (ag:ActiveGateVersion {version: $version})
        SET ag.title = $title,
            ag.source_url = $source_url,
            ag.last_seen = datetime()
        RETURN ag
        """
        try:
            result = self.graph_conn.execute(query, {
                'version': version,
                'title': title,
                'source_url': source_url
            })
            return result is not None
        except Exception as e:
            logger.error(f"Error ensuring ActiveGate release node: {e}")
            return False
    
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
        # Predicate format: '<component>_<statement_type>', e.g. 'activegate_compatible'
        parts = fact.predicate.split('_')
        if len(parts) < 2:
            return False

        component = parts[0]
        statement_type = '_'.join(parts[1:])  # e.g. 'compatible', 'end_of_support'

        # Map statement types to graph relationship names
        rel_map = {
            'compatible': 'COMPATIBLE_WITH',
            'requires': 'REQUIRES',
            'deprecated': 'DEPRECATED_IN',
            'requires_upgrade': 'REQUIRES_UPGRADE',
            'end_of_support': 'END_OF_SUPPORT',
            'incompatible': 'INCOMPATIBLE_WITH',
            'supported': 'SUPPORTED_BY',
        }
        relationship_type = rel_map.get(statement_type, statement_type.upper())

        if component == 'activegate':
            return self._insert_activegate_compatibility(fact, relationship_type)
        elif component == 'os':
            return self._insert_os_compatibility(fact, relationship_type)
        elif component == 'extension':
            return self._insert_extension_compatibility(fact, relationship_type)
        elif component == 'managed_cluster':
            return self._insert_managed_cluster_compatibility(fact, relationship_type)

        return False

    def _insert_activegate_compatibility(self, fact: ExtractedFact, relationship_type: str) -> bool:
        """Insert ActiveGate node and, when an object version exists, a typed relationship to it."""
        try:
            # Always ensure the subject ActiveGate node exists
            self.graph_conn.execute(
                "MERGE (ag:ActiveGateVersion {version: $version}) SET ag.last_seen = datetime()",
                {'version': fact.subject}
            )

            # If we have an object (related version), create the typed relationship
            if fact.object and fact.object != 'activegate':
                query = f"""
                MERGE (ag:ActiveGateVersion {{version: $ag_version}})
                MERGE (mc:ManagedClusterVersion {{version: $mc_version}})
                MERGE (ag)-[r:{relationship_type}]->(mc)
                SET r.source_url = $source_url,
                    r.confidence  = $confidence,
                    r.raw_text    = $raw_text,
                    r.updated_at  = datetime()
                RETURN r
                """
                self.graph_conn.execute(query, {
                    'ag_version':  fact.subject,
                    'mc_version':  fact.object,
                    'source_url':  fact.source_url,
                    'confidence':  fact.confidence,
                    'raw_text':    fact.source_text,
                })
            return True
        except Exception as e:
            logger.error(f"Error inserting ActiveGate compatibility: {e}")
            return False

    def _insert_os_compatibility(self, fact: ExtractedFact, relationship_type: str) -> bool:
        """Insert OS node and link it to the ActiveGate version via SUPPORTED_BY."""
        try:
            # Parse 'family version' from subject, e.g. 'linux 8' or just 'linux'
            parts = fact.subject.split() if fact.subject else []
            os_name = parts[0] if parts else 'Unknown'
            os_ver = parts[1] if len(parts) > 1 else 'unknown'

            self.graph_conn.execute(
                "MERGE (os:OSVersion {os_name: $os_name, version: $version}) SET os.last_seen = datetime()",
                {'os_name': os_name, 'version': os_ver}
            )

            if fact.object:
                query = """
                MERGE (ag:ActiveGateVersion {version: $ag_version})
                MERGE (os:OSVersion {os_name: $os_name, version: $os_version})
                MERGE (ag)-[r:SUPPORTED_BY]->(os)
                SET r.source_url = $source_url,
                    r.confidence  = $confidence,
                    r.updated_at  = datetime()
                RETURN r
                """
                self.graph_conn.execute(query, {
                    'ag_version': fact.object,
                    'os_name':    os_name,
                    'os_version': os_ver,
                    'source_url': fact.source_url,
                    'confidence': fact.confidence,
                })
            return True
        except Exception as e:
            logger.error(f"Error inserting OS compatibility: {e}")
            return False

    def _insert_extension_compatibility(self, fact: ExtractedFact, relationship_type: str) -> bool:
        """Insert Extension node and link to ActiveGate via the appropriate relationship."""
        try:
            ext_id = fact.subject or 'unknown'
            ag_version = fact.object

            self.graph_conn.execute(
                "MERGE (ext:Extension {id: $ext_id}) SET ext.last_seen = datetime()",
                {'ext_id': ext_id}
            )

            if ag_version:
                query = f"""
                MERGE (ag:ActiveGateVersion {{version: $ag_version}})
                MERGE (ext:Extension {{id: $ext_id}})
                MERGE (ag)-[r:{relationship_type}]->(ext)
                SET r.source_url = $source_url,
                    r.confidence  = $confidence,
                    r.updated_at  = datetime()
                RETURN r
                """
                self.graph_conn.execute(query, {
                    'ag_version': ag_version,
                    'ext_id':     ext_id,
                    'source_url': fact.source_url,
                    'confidence': fact.confidence,
                })
            return True
        except Exception as e:
            logger.error(f"Error inserting extension compatibility: {e}")
            return False

    def _insert_managed_cluster_compatibility(self, fact: ExtractedFact, relationship_type: str) -> bool:
        """Insert ManagedClusterVersion node and link to ActiveGate via the appropriate relationship."""
        try:
            self.graph_conn.execute(
                "MERGE (mc:ManagedClusterVersion {version: $version}) SET mc.last_seen = datetime()",
                {'version': fact.subject}
            )

            if fact.object:
                query = f"""
                MERGE (ag:ActiveGateVersion {{version: $ag_version}})
                MERGE (mc:ManagedClusterVersion {{version: $mc_version}})
                MERGE (ag)-[r:{relationship_type}]->(mc)
                SET r.source_url = $source_url,
                    r.confidence  = $confidence,
                    r.updated_at  = datetime()
                RETURN r
                """
                self.graph_conn.execute(query, {
                    'ag_version': fact.object,
                    'mc_version': fact.subject,
                    'source_url': fact.source_url,
                    'confidence': fact.confidence,
                })
            return True
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
