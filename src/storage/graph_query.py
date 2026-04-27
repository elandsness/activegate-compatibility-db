import logging
from typing import List, Dict, Optional
from src.storage.graph_connection import GraphConnection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GraphQuery:
    """Queries the Neo4j graph for compatibility information."""
    
    def __init__(self, graph_conn: GraphConnection):
        """
        Initialize graph query engine.
        
        Args:
            graph_conn: GraphConnection instance
        """
        self.graph_conn = graph_conn
    
    def check_activegate_compatibility(self, 
                                      activegate_version: str,
                                      managed_version: str,
                                      os_family: str = None,
                                      extensions: List[str] = None) -> Dict:
        """
        Check if an ActiveGate version is compatible with a Managed cluster.
        
        Args:
            activegate_version: ActiveGate version (e.g., '1.335')
            managed_version: Managed cluster version (e.g., '1.335')
            os_family: Operating system family (e.g., 'windows', 'linux')
            extensions: List of extension IDs to check
        
        Returns:
            Dict with compatibility status, issues, and recommendations
        """
        issues = []
        warnings = []
        recommendations = []
        
        # Check if ActiveGate version exists in the graph
        ag_query = "MATCH (ag:ActiveGateVersion {version: $version}) RETURN ag"
        ag_result = self.graph_conn.execute(ag_query, {'version': activegate_version})
        
        if not ag_result:
            issues.append(f"ActiveGate version {activegate_version} not found in compatibility database")
            return {
                'status': 'NO_GO',
                'activegate_version': activegate_version,
                'managed_version': managed_version,
                'issues': issues,
                'warnings': warnings,
                'recommendations': recommendations,
                'confidence': 0.0
            }
        
        # Check Managed cluster compatibility
        managed_query = """
        MATCH (ag:ActiveGateVersion {version: $ag_version})
        MATCH (mc:ManagedClusterVersion {version: $mc_version})
        OPTIONAL MATCH (ag)-[r:COMPATIBLE_WITH|REQUIRES]->(mc)
        RETURN r
        """
        
        managed_result = self.graph_conn.execute(
            managed_query,
            {'ag_version': activegate_version, 'mc_version': managed_version}
        )
        
        if not managed_result:
            warnings.append(f"No explicit compatibility data found for AG {activegate_version} with Managed {managed_version}")
        
        # Check for deprecations
        deprecated_query = """
        MATCH (ag:ActiveGateVersion {version: $version})
        MATCH (ag)-[r:DEPRECATED_IN]->(mc:ManagedClusterVersion)
        RETURN mc
        """
        
        deprecated_result = self.graph_conn.execute(
            deprecated_query,
            {'version': activegate_version}
        )
        
        if deprecated_result:
            issues.append(f"ActiveGate {activegate_version} is deprecated")
            recommendations.append(f"Upgrade to a newer ActiveGate version")
        
        # Check OS compatibility if specified
        if os_family:
            os_compat = self.check_os_compatibility(activegate_version, os_family)
            if not os_compat['compatible']:
                issues.extend(os_compat['issues'])
            else:
                warnings.extend(os_compat['warnings'])
        
        # Check extension compatibility if specified
        if extensions:
            ext_issues = self.check_extensions_compatibility(
                activegate_version,
                extensions
            )
            issues.extend(ext_issues['failed'])
            warnings.extend(ext_issues['warnings'])
        
        # Determine overall status
        if issues:
            status = 'NO_GO'
        elif warnings:
            status = 'GO_WITH_CAUTION'
        else:
            status = 'GO'
        
        return {
            'status': status,
            'activegate_version': activegate_version,
            'managed_version': managed_version,
            'os_family': os_family,
            'issues': issues,
            'warnings': warnings,
            'recommendations': recommendations,
            'confidence': self._calculate_confidence(
                len(issues),
                len(warnings),
                len(recommendations)
            )
        }
    
    def check_os_compatibility(self, activegate_version: str, os_family: str) -> Dict:
        """
        Check OS compatibility for an ActiveGate version.
        
        Args:
            activegate_version: ActiveGate version
            os_family: OS family (windows, linux, etc.)
        
        Returns:
            Dict with compatibility status
        """
        query = """
        MATCH (ag:ActiveGateVersion {version: $ag_version})
        MATCH (os:OSVersion)
        WHERE tolower(os.os_name) = tolower($os_family)
        OPTIONAL MATCH (ag)-[r:SUPPORTED_BY]->(os)
        RETURN os, r
        """
        
        result = self.graph_conn.execute(
            query,
            {'ag_version': activegate_version, 'os_family': os_family}
        )
        
        issues = []
        warnings = []
        
        if not result:
            issues.append(f"No OS compatibility data found for {os_family}")
            compatible = False
        else:
            # Check if specific OS version is supported
            compatible = True
            for record in result:
                if not record.get('r'):
                    warnings.append(f"No explicit support for {os_family} with AG {activegate_version}")
        
        return {
            'compatible': compatible,
            'os_family': os_family,
            'issues': issues,
            'warnings': warnings
        }
    
    def check_extensions_compatibility(self, 
                                      activegate_version: str,
                                      extension_ids: List[str]) -> Dict:
        """
        Check if extensions are compatible with an ActiveGate version.
        
        Args:
            activegate_version: ActiveGate version
            extension_ids: List of extension IDs
        
        Returns:
            Dict with failed extensions and warnings
        """
        failed = []
        warnings = []
        passed = []
        
        for ext_id in extension_ids:
            query = """
            MATCH (ag:ActiveGateVersion {version: $ag_version})
            MATCH (ext:Extension {id: $ext_id})
            OPTIONAL MATCH (ag)-[r:COMPATIBLE_WITH]->(ext)
            OPTIONAL MATCH (ag)-[r2:INCOMPATIBLE_WITH]->(ext)
            RETURN r, r2
            """
            
            result = self.graph_conn.execute(
                query,
                {'ag_version': activegate_version, 'ext_id': ext_id}
            )
            
            if result:
                for record in result:
                    if record.get('r2'):
                        failed.append(f"Extension {ext_id} is incompatible with AG {activegate_version}")
                    elif record.get('r'):
                        passed.append(ext_id)
                    else:
                        warnings.append(f"No compatibility data for extension {ext_id}")
            else:
                warnings.append(f"Extension {ext_id} not found in database")
        
        return {
            'failed': failed,
            'warnings': warnings,
            'passed': passed
        }
    
    def get_compatible_activegate_versions(self, managed_version: str) -> List[str]:
        """Get all ActiveGate versions compatible with a Managed cluster version."""
        query = """
        MATCH (ag:ActiveGateVersion)-[r:COMPATIBLE_WITH|REQUIRES]->(mc:ManagedClusterVersion {version: $managed_version})
        RETURN DISTINCT ag.version as version
        ORDER BY ag.version DESC
        """
        
        try:
            results = self.graph_conn.execute(query, {'managed_version': managed_version})
            return [record['version'] for record in results]
        except Exception as e:
            logger.error(f"Error getting compatible AG versions: {e}")
            return []
    
    def get_upgrade_paths(self, from_version: str, to_version: str) -> List[Dict]:
        """
        Find upgrade paths from one ActiveGate version to another.
        
        Args:
            from_version: Starting version
            to_version: Target version
        
        Returns:
            List of upgrade paths
        """
        query = """
        MATCH path = (from:ActiveGateVersion {version: $from_version})
                     -[:UPGRADEABLE_TO*1..10]->
                     (to:ActiveGateVersion {version: $to_version})
        RETURN path
        LIMIT 5
        """
        
        try:
            results = self.graph_conn.execute(
                query,
                {'from_version': from_version, 'to_version': to_version}
            )
            return [{'path': str(record['path'])} for record in results]
        except Exception as e:
            logger.error(f"Error getting upgrade paths: {e}")
            return []
    
    def get_entity_details(self, entity_type: str, entity_id: str) -> Dict:
        """
        Get detailed information about a specific entity (version, extension, etc.).
        
        Args:
            entity_type: Type of entity (activegate, extension, os, etc.)
            entity_id: ID/version of the entity
        
        Returns:
            Dict with entity details
        """
        if entity_type.lower() == 'activegate':
            node_type = 'ActiveGateVersion'
            id_field = 'version'
        elif entity_type.lower() == 'extension':
            node_type = 'Extension'
            id_field = 'id'
        elif entity_type.lower() == 'os':
            node_type = 'OSVersion'
            id_field = 'os_name'
        else:
            return {'error': f"Unknown entity type: {entity_type}"}
        
        query = f"""
        MATCH (e:{node_type} {{{id_field}: $id}})
        OPTIONAL MATCH (e)-[r1]->()
        OPTIONAL MATCH (e)<-[r2]-()
        RETURN e, r1, r2
        """
        
        try:
            results = self.graph_conn.execute(query, {'id': entity_id})
            if not results:
                return {'error': f"{entity_type} {entity_id} not found"}
            
            # Aggregate results
            details = {'entity_type': entity_type, 'id': entity_id}
            out_relationships = []
            in_relationships = []
            
            for record in results:
                if record.get('r1'):
                    out_relationships.append(str(record['r1']))
                if record.get('r2'):
                    in_relationships.append(str(record['r2']))
            
            details['outgoing_relationships'] = out_relationships
            details['incoming_relationships'] = in_relationships
            
            return details
        except Exception as e:
            logger.error(f"Error getting entity details: {e}")
            return {'error': str(e)}
    
    @staticmethod
    def _calculate_confidence(issues: int, warnings: int, recommendations: int) -> float:
        """Calculate overall confidence score for compatibility check."""
        if issues > 0:
            return max(0.0, 1.0 - (issues * 0.2))
        elif warnings > 0:
            return max(0.5, 1.0 - (warnings * 0.1))
        else:
            return 1.0
