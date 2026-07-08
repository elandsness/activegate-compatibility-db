import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CompatibilityStatus(Enum):
    GO = "GO"
    GO_WITH_CAUTION = "GO_WITH_CAUTION"
    NO_GO = "NO_GO"
    UNKNOWN = "UNKNOWN"


@dataclass
class CompatibilityIssue:
    """Represents a single compatibility issue found during reasoning."""

    severity: str  # 'critical', 'warning', 'info'
    category: str  # 'version', 'os', 'extension', 'managed_cluster', 'deprecation'
    message: str
    source_url: Optional[str] = None
    source_text: Optional[str] = None
    recommendation: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "source_url": self.source_url,
            "source_text": self.source_text,
            "recommendation": self.recommendation,
        }


@dataclass
class CompatibilityResult:
    """Complete result of a compatibility check."""

    status: CompatibilityStatus
    current_activegate_version: str
    target_activegate_version: str
    managed_cluster_version: str = "N/A"
    issues: List[CompatibilityIssue] = field(default_factory=list)
    warnings: List[CompatibilityIssue] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    citations: List[Dict] = field(default_factory=list)
    confidence: float = 0.0
    checked_factors: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "status": self.status.value,
            "current_activegate_version": self.current_activegate_version,
            "target_activegate_version": self.target_activegate_version,
            "managed_cluster_version": self.managed_cluster_version,
            "issues": [i.to_dict() for i in self.issues],
            "warnings": [w.to_dict() for w in self.warnings],
            "recommendations": self.recommendations,
            "citations": self.citations,
            "confidence": self.confidence,
            "checked_factors": self.checked_factors,
        }


class CompatibilityReasoner:
    """
    Core reasoning engine for determining ActiveGate upgrade compatibility.
    Applies rules and logic to make go/no-go decisions.
    """

    def __init__(self, graph_query=None):
        """
        Initialize the reasoner.

        Args:
            graph_query: Optional GraphQuery instance for database lookups
        """
        self.graph_query = graph_query
        self.rules = self._load_compatibility_rules()

    def _load_compatibility_rules(self) -> Dict:
        """Load compatibility rules and thresholds."""
        return {
            "min_confidence_for_go": 0.8,
            "min_confidence_for_caution": 0.5,
            "critical_issues": [
                "incompatible",
                "end_of_support",
                "unsupported_version",
            ],
            "warning_issues": [
                "deprecated",
                "requires_upgrade",
                "low_confidence",
            ],
            "os_version_check": True,
            "extension_version_check": True,
            "managed_cluster_check": True,
        }

    def check_upgrade_compatibility(
        self,
        current_version: str,
        target_version: str,
        os_family: Optional[str] = None,
        os_version: Optional[str] = None,
        managed_cluster_version: Optional[str] = None,
        extensions: Optional[List[Dict]] = None,
        use_graph: bool = False,
    ) -> CompatibilityResult:
        """
        Check if an upgrade from current to target ActiveGate version is compatible.

        Args:
            current_version: Current ActiveGate version (e.g., '1.330')
            target_version: Target ActiveGate version (e.g., '1.335')
            os_family: Operating system family (windows, linux, etc.)
            os_version: Specific OS version
            managed_cluster_version: Dynatrace Managed cluster version
            extensions: List of dicts with extension info {'id': str, 'version': str}
            use_graph: Whether to query the graph database

        Returns:
            CompatibilityResult with go/no-go decision and details
        """
        logger.info(f"Checking upgrade: {current_version} -> {target_version}")

        issues = []
        warnings = []
        citations = []
        checked_factors = {}

        # 1. Check version compatibility
        version_issues, version_warnings = self._check_version_compatibility(
            current_version, target_version
        )
        issues.extend(version_issues)
        warnings.extend(version_warnings)
        checked_factors["version"] = "checked"

        # 2. Check OS compatibility
        if os_family:
            os_issues, os_warnings = self._check_os_compatibility(
                target_version, os_family, os_version
            )
            issues.extend(os_issues)
            warnings.extend(os_warnings)
            checked_factors["os"] = "checked"

        # 3. Check Managed cluster compatibility
        if managed_cluster_version:
            mc_issues, mc_warnings = self._check_managed_cluster_compatibility(
                target_version, managed_cluster_version
            )
            issues.extend(mc_issues)
            warnings.extend(mc_warnings)
            checked_factors["managed_cluster"] = "checked"

        # 4. Check extension compatibility
        if extensions:
            ext_issues, ext_warnings = self._check_extension_compatibility(
                target_version, extensions
            )
            issues.extend(ext_issues)
            warnings.extend(ext_warnings)
            checked_factors["extensions"] = "checked"

        # 5. Check for deprecations
        dep_issues, dep_warnings = self._check_deprecations(target_version)
        issues.extend(dep_issues)
        warnings.extend(dep_warnings)
        checked_factors["deprecations"] = "checked"

        # 6. Check for end-of-support
        eos_issues = self._check_end_of_support(target_version)
        issues.extend(eos_issues)
        checked_factors["end_of_support"] = "checked"

        # 7. Query graph if available and requested
        if use_graph and self.graph_query:
            graph_result = self._check_via_graph(
                current_version,
                target_version,
                managed_cluster_version,
                os_family,
                extensions,
            )
            issues.extend(graph_result.get("issues", []))
            warnings.extend(graph_result.get("warnings", []))
            citations.extend(graph_result.get("citations", []))

        # 8. Determine final status
        status = self._determine_status(issues, warnings)

        # 9. Generate recommendations
        recommendations = self._generate_recommendations(issues, warnings)

        # 10. Calculate confidence
        confidence = self._calculate_confidence(issues, warnings)

        return CompatibilityResult(
            status=status,
            current_activegate_version=current_version,
            target_activegate_version=target_version,
            managed_cluster_version=managed_cluster_version or "N/A",
            issues=issues,
            warnings=warnings,
            recommendations=recommendations,
            citations=citations,
            confidence=confidence,
            checked_factors=checked_factors,
        )

    def _check_version_compatibility(self, current: str, target: str) -> tuple:
        """Check if the version upgrade is valid."""
        issues = []
        warnings = []

        try:
            current_parts = [int(x) for x in current.split(".")]
            target_parts = [int(x) for x in target.split(".")]

            # Target should be >= current
            if target_parts < current_parts:
                issues.append(
                    CompatibilityIssue(
                        severity="critical",
                        category="version",
                        message=f"Target version {target} is older than current version {current}",
                        recommendation="Select a target version >= current version",
                    )
                )
            elif target_parts == current_parts:
                warnings.append(
                    CompatibilityIssue(
                        severity="warning",
                        category="version",
                        message=f"Target version {target} is the same as current version {current}",
                        recommendation="No upgrade needed if already on this version",
                    )
                )
            else:
                # Valid upgrade path
                warnings.append(
                    CompatibilityIssue(
                        severity="info",
                        category="version",
                        message=f"Upgrading from {current} to {target}",
                        recommendation=None,
                    )
                )
        except Exception as e:
            issues.append(
                CompatibilityIssue(
                    severity="critical",
                    category="version",
                    message=f"Could not parse version: {e}",
                    recommendation="Verify version format (e.g., 1.335)",
                )
            )

        return issues, warnings

    def _check_os_compatibility(
        self, ag_version: str, os_family: str, os_version: str = None
    ) -> tuple:
        """Check OS compatibility for ActiveGate."""
        issues = []
        warnings = []

        # Known supported OS versions (from documentation patterns)
        supported_os = {
            "windows": ["2016", "2019", "2022"],
            "linux": ["7", "8", "9", "20.04", "22.04"],
            "rhel": ["7", "8", "9"],
            "centos": ["7", "8"],
            "ubuntu": ["20.04", "22.04"],
        }

        os_family_lower = os_family.lower()

        if os_family_lower in supported_os:
            if os_version:
                # Check specific version
                version_num = "".join(c for c in os_version if c.isdigit())
                supported = supported_os[os_family_lower]

                if not any(sv in version_num for sv in supported):
                    warnings.append(
                        CompatibilityIssue(
                            severity="warning",
                            category="os",
                            message=f"OS version {os_version} may not be explicitly supported for AG {ag_version}",
                            recommendation=f'Ensure OS is one of: {", ".join(supported)}',
                        )
                    )
            else:
                warnings.append(
                    CompatibilityIssue(
                        severity="info",
                        category="os",
                        message=f"OS family {os_family} supported but specific version not checked",
                        recommendation="Provide OS version for detailed compatibility check",
                    )
                )
        else:
            warnings.append(
                CompatibilityIssue(
                    severity="warning",
                    category="os",
                    message=f"OS family {os_family} not in known supported list",
                    recommendation="Verify OS is supported by Dynatrace",
                )
            )

        return issues, warnings

    def _check_managed_cluster_compatibility(
        self, ag_version: str, managed_version: str
    ) -> tuple:
        """Check Managed cluster version compatibility."""
        issues = []
        warnings = []

        try:
            ag_parts = [int(x) for x in ag_version.split(".")]
            mc_parts = [int(x) for x in managed_version.split(".")]

            # ActiveGate typically requires Managed version >= AG version - 5
            min_managed = [ag_parts[0], max(0, ag_parts[1] - 5), 0]

            if mc_parts < min_managed:
                issues.append(
                    CompatibilityIssue(
                        severity="critical",
                        category="managed_cluster",
                        message=f"Managed cluster {managed_version} may be too old for AG {ag_version}",
                        recommendation=f"Upgrade Managed cluster to at least {min_managed[0]}.{min_managed[1]}.0",
                    )
                )
            else:
                warnings.append(
                    CompatibilityIssue(
                        severity="info",
                        category="managed_cluster",
                        message=f"AG {ag_version} compatible with Managed {managed_version}",
                        recommendation=None,
                    )
                )
        except Exception as e:
            warnings.append(
                CompatibilityIssue(
                    severity="warning",
                    category="managed_cluster",
                    message=f"Could not verify Managed cluster compatibility: {e}",
                    recommendation="Manually verify Managed cluster version compatibility",
                )
            )

        return issues, warnings

    def _check_extension_compatibility(
        self, ag_version: str, extensions: List[Dict]
    ) -> tuple:
        """Check extension compatibility."""
        issues = []
        warnings = []

        for ext in extensions:
            ext_id = ext.get("id", "unknown")
            ext_version = ext.get("version", "unknown")

            # Check for known incompatible extensions or version requirements
            # This is a simplified check - in production would query graph/knowledge base

            if ext_version:
                # Simple version parsing check
                try:
                    ext_parts = [int(x) for x in ext_version.split(".")]
                    ag_parts = [int(x) for x in ag_version.split(".")]

                    # If extension is much newer than AG, might have issues
                    if ext_parts[0] > ag_parts[0]:
                        warnings.append(
                            CompatibilityIssue(
                                severity="warning",
                                category="extension",
                                message=f"Extension {ext_id} v{ext_version} may require newer AG",
                                recommendation="Verify extension supports AG version",
                            )
                        )
                except (ValueError, TypeError):
                    warnings.append(
                        CompatibilityIssue(
                            severity="info",
                            category="extension",
                            message=f"Could not verify extension {ext_id} compatibility",
                            recommendation=None,
                        )
                    )

        return issues, warnings

    def _check_deprecations(self, version: str) -> tuple:
        """Check for deprecated versions."""
        issues = []
        warnings = []

        # Known deprecated versions (would come from NLP extraction in production)
        deprecated_versions = ["1.300", "1.310", "1.320", "1.325"]

        if version in deprecated_versions:
            warnings.append(
                CompatibilityIssue(
                    severity="warning",
                    category="deprecation",
                    message=f"ActiveGate {version} is deprecated",
                    recommendation="Consider upgrading to a newer version",
                )
            )

        return issues, warnings

    def _check_end_of_support(self, version: str) -> List[CompatibilityIssue]:
        """Check for end-of-support versions."""
        issues = []

        # Known end-of-support versions
        eos_versions = ["1.280", "1.290", "1.300"]

        if version in eos_versions:
            issues.append(
                CompatibilityIssue(
                    severity="critical",
                    category="end_of_support",
                    message=f"ActiveGate {version} has reached end of support",
                    recommendation="Upgrade to a supported version immediately",
                )
            )

        return issues

    def _check_via_graph(
        self,
        current: str,
        target: str,
        managed: str = None,
        os: str = None,
        extensions: list = None,
    ) -> Dict:
        """Check compatibility via graph database."""
        if not self.graph_query:
            return {}

        try:
            result = self.graph_query.check_activegate_compatibility(
                activegate_version=target,
                managed_version=managed or "1.335",
                os_family=os,
                extensions=([e.get("id") for e in extensions] if extensions else None),
            )

            # Convert graph result to issues
            issues = []
            warnings = []
            citations = []

            for issue_msg in result.get("issues", []):
                issues.append(
                    CompatibilityIssue(
                        severity="critical",
                        category="graph",
                        message=issue_msg,
                        recommendation=None,
                    )
                )

            for warn_msg in result.get("warnings", []):
                warnings.append(
                    CompatibilityIssue(
                        severity="warning",
                        category="graph",
                        message=warn_msg,
                        recommendation=None,
                    )
                )

            return {
                "issues": issues,
                "warnings": warnings,
                "citations": citations,
            }
        except Exception as e:
            logger.error(f"Error checking via graph: {e}")
            return {}

    def _determine_status(
        self,
        issues: List[CompatibilityIssue],
        warnings: List[CompatibilityIssue],
    ) -> CompatibilityStatus:
        """Determine final compatibility status."""
        # Critical issues = NO_GO
        critical_issues = [i for i in issues if i.severity == "critical"]
        if critical_issues:
            return CompatibilityStatus.NO_GO

        # Warnings = GO_WITH_CAUTION
        if warnings:
            return CompatibilityStatus.GO_WITH_CAUTION

        # Clean = GO
        return CompatibilityStatus.GO

    def _generate_recommendations(
        self,
        issues: List[CompatibilityIssue],
        warnings: List[CompatibilityIssue],
    ) -> List[str]:
        """Generate recommendations based on issues and warnings."""
        recommendations = []

        for issue in issues:
            if issue.recommendation:
                recommendations.append(issue.recommendation)

        for warning in warnings:
            if warning.recommendation and warning.recommendation not in recommendations:
                recommendations.append(warning.recommendation)

        return recommendations

    def _calculate_confidence(
        self,
        issues: List[CompatibilityIssue],
        warnings: List[CompatibilityIssue],
    ) -> float:
        """Calculate confidence score."""
        base_confidence = 1.0

        # Reduce for critical issues
        critical_count = len([i for i in issues if i.severity == "critical"])
        base_confidence -= critical_count * 0.3

        # Reduce for warnings
        warning_count = len(warnings)
        base_confidence -= warning_count * 0.1

        return max(0.0, min(1.0, base_confidence))
