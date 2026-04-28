import logging
from typing import Optional
from neo4j import GraphDatabase, Session, Driver
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GraphConnection:
    """Manages Neo4j graph database connections."""
    
    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        """
        Initialize graph connection.
        
        Args:
            uri: Neo4j connection URI (e.g., 'bolt://localhost:7687')
            user: Username for authentication
            password: Password for authentication
            database: Database name (default: 'neo4j')
        """
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.driver: Optional[Driver] = None
    
    def connect(self) -> bool:
        """Establish connection to Neo4j."""
        try:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                database=self.database
            )
            # Test the connection
            with self.driver.session() as session:
                session.run("RETURN 1")
            logger.info(f"Successfully connected to Neo4j at {self.uri}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            return False
    
    def disconnect(self):
        """Close connection to Neo4j."""
        if self.driver:
            self.driver.close()
            logger.info("Disconnected from Neo4j")
    
    @contextmanager
    def get_session(self) -> Session:
        """Get a Neo4j session context manager."""
        if not self.driver:
            raise RuntimeError("Not connected to Neo4j. Call connect() first.")
        
        session = self.driver.session()
        try:
            yield session
        finally:
            session.close()
    
    def execute(self, query: str, parameters: dict = None) -> list:
        """Execute a Cypher query and return results."""
        if not self.driver:
            raise RuntimeError("Not connected to Neo4j. Call connect() first.")
        
        with self.get_session() as session:
            try:
                result = session.run(query, parameters)
                records = list(result)
                logger.debug(f"Executed query, got {len(records)} records")
                return records
            except Exception as e:
                logger.error(f"Error executing query: {e}")
                raise
    
    def create_indexes(self):
        """Create necessary indexes for performance."""
        try:
            with self.get_session() as session:
                # Index for ActiveGate versions
                session.run(
                    "CREATE INDEX idx_activegate_version IF NOT EXISTS FOR (n:ActiveGateVersion) ON (n.version)"
                )
                
                # Index for Managed cluster versions
                session.run(
                    "CREATE INDEX idx_managed_version IF NOT EXISTS FOR (n:ManagedClusterVersion) ON (n.version)"
                )
                
                # Index for OS versions
                session.run(
                    "CREATE INDEX idx_os_version IF NOT EXISTS FOR (n:OSVersion) ON (n.os_name, n.version)"
                )
                
                # Index for extensions
                session.run(
                    "CREATE INDEX idx_extension_id IF NOT EXISTS FOR (n:Extension) ON (n.id, n.version)"
                )
                
                logger.info("Database indexes created successfully")
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")
    
    def clear_database(self):
        """Clear all data from the database (USE WITH CAUTION)."""
        try:
            with self.get_session() as session:
                session.run("MATCH (n) DETACH DELETE n")
                logger.warning("Database cleared")
        except Exception as e:
            logger.error(f"Error clearing database: {e}")
    
    def get_stats(self) -> dict:
        """Get basic statistics about the graph."""
        try:
            with self.get_session() as session:
                stats = {}
                
                # Count nodes by type
                node_types = ['ActiveGateVersion', 'ManagedClusterVersion', 'OSVersion', 'Extension']
                for node_type in node_types:
                    result = session.run(f"MATCH (n:{node_type}) RETURN count(n) as count")
                    count = result.single()['count']
                    stats[f"{node_type}_count"] = count
                
                # Count relationships
                result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
                stats['relationships_count'] = result.single()['count']
                
                return stats
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}
