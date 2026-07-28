import logging
from typing import Dict, List, Optional, Tuple

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

    def check_activegate_compatibility(
        self,
        activegate_version: str,
        managed_version: str,
        os_family: str = None,
        extensions: List[str] = None,
    ) -> Dict:
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
        ag_result = self.graph_conn.execute(ag_query, {"version": activegate_version})

        if not ag_result:
            issues.append(
                f"ActiveGate version {activegate_version} not found in compatibility database"
            )
            return {
                "status": "NO_GO",
                "activegate_version": activegate_version,
                "managed_version": managed_version,
                "issues": issues,
                "warnings": warnings,
                "recommendations": recommendations,
                "confidence": 0.0,
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
            {"ag_version": activegate_version, "mc_version": managed_version},
        )

        if not managed_result:
            warnings.append(
                f"No explicit compatibility data found for AG {activegate_version} with Managed {managed_version}"
            )

        # Check for deprecations
        deprecated_query = """
        MATCH (ag:ActiveGateVersion {version: $version})
        MATCH (ag)-[r:DEPRECATED_IN]->(mc:ManagedClusterVersion)
        RETURN mc
        """

        deprecated_result = self.graph_conn.execute(
            deprecated_query, {"version": activegate_version}
        )

        if deprecated_result:
            issues.append(f"ActiveGate {activegate_version} is deprecated")
            recommendations.append("Upgrade to a newer ActiveGate version")

        # Check OS compatibility if specified
        if os_family:
            os_compat = self.check_os_compatibility(activegate_version, os_family)
            if not os_compat["compatible"]:
                issues.extend(os_compat["issues"])
            else:
                warnings.extend(os_compat["warnings"])

        # Check extension compatibility if specified
        unknown_extensions = []
        if extensions:
            ext_issues = self.check_extensions_compatibility(
                activegate_version,
                extensions,
                managed_version=managed_version,
            )
            issues.extend(ext_issues["failed"])
            warnings.extend(ext_issues["warnings"])
            unknown_extensions = ext_issues.get("unknown", [])

        # Determine overall status
        if issues:
            status = "NO_GO"
        elif warnings:
            status = "GO_WITH_CAUTION"
        else:
            status = "GO"

        return {
            "status": status,
            "activegate_version": activegate_version,
            "managed_version": managed_version,
            "os_family": os_family,
            "issues": issues,
            "warnings": warnings,
            "unknown_extensions": unknown_extensions,
            "recommendations": recommendations,
            "confidence": self._calculate_confidence(
                len(issues), len(warnings), len(recommendations)
            ),
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
            query, {"ag_version": activegate_version, "os_family": os_family}
        )

        issues = []
        warnings = []

        if not result:
            issues.append(f"No OS compatibility data found for {os_family}")
            compatible = False
        else:
            # Rows contain all OS nodes for this family; warn once only when
            # none of them has an explicit SUPPORTED_BY relationship.
            compatible = True
            has_explicit_support = any(record.get("r") for record in result)
            if not has_explicit_support:
                warnings.append(
                    f"No explicit support for {os_family} with AG {activegate_version}"
                )

        return {
            "compatible": compatible,
            "os_family": os_family,
            "issues": issues,
            "warnings": warnings,
        }

    def check_extensions_compatibility(
        self,
        activegate_version: str,
        extension_ids: List[str],
        managed_version: Optional[str] = None,
        min_confidence: float = 0.7,
    ) -> Dict:
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
        unknown = []
        passed = []

        for ext_id in extension_ids:
            result = self._check_extension2_constraint(
                extension_id=ext_id,
                activegate_version=activegate_version,
                managed_version=managed_version,
                min_confidence=min_confidence,
            )

            status = result.get("status")
            if status == "FAILED":
                failed.append(result.get("message"))
            elif status == "UNKNOWN":
                unknown.append(result.get("message"))
            elif status == "WARN":
                warnings.append(result.get("message"))
            elif status == "PASSED":
                passed.append(ext_id)

        return {
            "failed": failed,
            "warnings": warnings,
            "unknown": unknown,
            "passed": passed,
        }

    def _check_extension2_constraint(
        self,
        extension_id: str,
        activegate_version: str,
        managed_version: Optional[str],
        min_confidence: float,
    ) -> Dict[str, str]:
        query = """
        MATCH (item:HubItem)
        WHERE item.extension_type = 'extension-2'
          AND coalesce(item.active, true) = true
          AND (item.slug = $ext_id OR item.id = $ext_id)
        OPTIONAL MATCH (item)-[:HAS_RELEASE]->(release:HubItemRelease)
        WITH item, release
        ORDER BY coalesce(release.published_at_epoch, 0) DESC
        WITH item, collect(release)[0] AS latest_release
        OPTIONAL MATCH (latest_release)-[ag_req:REQUIRES_ACTIVEGATE]->(ag_target:ActiveGateVersion)
        OPTIONAL MATCH (latest_release)-[mc_req:REQUIRES_MANAGED]->(mc_target:ManagedClusterVersion)
        RETURN item.slug AS slug,
               item.title AS title,
               latest_release.version AS release_version,
               collect({
                 min_version: ag_req.min_version,
                 confidence: ag_req.confidence,
                 verified: ag_req.verified
               }) AS ag_constraints,
               collect({
                 min_version: mc_req.min_version,
                 confidence: mc_req.confidence,
                 verified: mc_req.verified
               }) AS mc_constraints
        """
        rows = self.graph_conn.execute(query, {"ext_id": extension_id})
        if not rows:
            return {
                "status": "WARN",
                "message": f"Extension {extension_id} not found in extension-2 catalog",
            }

        row = rows[0]
        title = row.get("title") or extension_id
        ag_constraints = self._normalize_constraints(
            row.get("ag_constraints", []), min_confidence
        )
        mc_constraints = self._normalize_constraints(
            row.get("mc_constraints", []), min_confidence
        )

        if not ag_constraints:
            return {
                "status": "UNKNOWN",
                "message": f"Extension {title} has no verified ActiveGate constraint data",
            }

        required_ag = self._max_version(ag_constraints)
        if self._compare_versions(activegate_version, required_ag) < 0:
            return {
                "status": "FAILED",
                "message": f"Extension {title} requires ActiveGate >= {required_ag} (target {activegate_version})",
            }

        if managed_version and mc_constraints:
            required_managed = self._max_version(mc_constraints)
            if self._compare_versions(managed_version, required_managed) < 0:
                return {
                    "status": "FAILED",
                    "message": f"Extension {title} requires Managed >= {required_managed} (cluster {managed_version})",
                }

        return {"status": "PASSED", "message": f"Extension {title} passed"}

    def _normalize_constraints(
        self, constraints: List[Dict], min_confidence: float
    ) -> List[str]:
        versions = []
        seen = set()
        for constraint in constraints:
            min_version = constraint.get("min_version")
            confidence = float(constraint.get("confidence") or 0.0)
            verified = bool(constraint.get("verified"))
            if not min_version:
                continue
            if not verified and confidence < min_confidence:
                continue
            if min_version in seen:
                continue
            seen.add(min_version)
            versions.append(min_version)
        return versions

    def _max_version(self, versions: List[str]) -> str:
        if not versions:
            return "0.0.0"
        return sorted(versions, key=self._version_key)[-1]

    def _compare_versions(self, left: str, right: str) -> int:
        lk = self._version_key(left)
        rk = self._version_key(right)
        if lk < rk:
            return -1
        if lk > rk:
            return 1
        return 0

    def _version_key(self, version: str) -> Tuple[int, ...]:
        parts = [int(p) for p in str(version).split(".") if p.isdigit()]
        if not parts:
            return (0,)
        # Pad to keep lexicographic tuple compare stable for 2/3 segment versions.
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])

    def get_compatible_activegate_versions(self, managed_version: str) -> List[str]:
        """Get all ActiveGate versions compatible with a Managed cluster version."""
        query = """
        MATCH (ag:ActiveGateVersion)-[r:COMPATIBLE_WITH|REQUIRES]->(mc:ManagedClusterVersion {version: $managed_version})
        RETURN DISTINCT ag.version as version
        ORDER BY ag.version DESC
        """

        try:
            results = self.graph_conn.execute(
                query, {"managed_version": managed_version}
            )
            return [record["version"] for record in results]
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
                query, {"from_version": from_version, "to_version": to_version}
            )
            return [{"path": str(record["path"])} for record in results]
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
        if entity_type.lower() == "activegate":
            node_type = "ActiveGateVersion"
            id_field = "version"
        elif entity_type.lower() == "extension":
            node_type = "Extension"
            id_field = "id"
        elif entity_type.lower() == "os":
            node_type = "OSVersion"
            id_field = "os_name"
        else:
            return {"error": f"Unknown entity type: {entity_type}"}

        query = f"""
        MATCH (e:{node_type} {{{id_field}: $id}})
        OPTIONAL MATCH (e)-[r1]->()
        OPTIONAL MATCH (e)<-[r2]-()
        RETURN e, r1, r2
        """

        try:
            results = self.graph_conn.execute(query, {"id": entity_id})
            if not results:
                return {"error": f"{entity_type} {entity_id} not found"}

            # Aggregate results
            details = {"entity_type": entity_type, "id": entity_id}
            out_relationships = []
            in_relationships = []

            for record in results:
                if record.get("r1"):
                    out_relationships.append(str(record["r1"]))
                if record.get("r2"):
                    in_relationships.append(str(record["r2"]))

            details["outgoing_relationships"] = out_relationships
            details["incoming_relationships"] = in_relationships

            return details
        except Exception as e:
            logger.error(f"Error getting entity details: {e}")
            return {"error": str(e)}

    @staticmethod
    def _calculate_confidence(
        issues: int, warnings: int, recommendations: int
    ) -> float:
        """Calculate overall confidence score for compatibility check."""
        if issues > 0:
            return max(0.0, 1.0 - (issues * 0.2))
        elif warnings > 0:
            return max(0.5, 1.0 - (warnings * 0.1))
        else:
            return 1.0
